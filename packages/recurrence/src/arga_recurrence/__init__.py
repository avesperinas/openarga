from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from dateutil import rrule as du
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "Day",
    "Freq",
    "Locale",
    "Occurrence",
    "Rule",
    "Weekday",
    "describe",
    "expand",
    "next_occurrence",
    "parse",
    "split",
    "split_exceptions",
    "to_rrule",
]

Freq = Literal["daily", "weekly", "monthly", "yearly"]
Weekday = Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

WEEKDAYS: tuple[Weekday, ...] = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_FREQS: dict[Freq, int] = {
    "daily": du.DAILY,
    "weekly": du.WEEKLY,
    "monthly": du.MONTHLY,
    "yearly": du.YEARLY,
}
_POSITIONS = {1, 2, 3, 4, 5, -1, -2, -3}
_MONTH_DAYS = set(range(1, 32)) | {-1, -2, -3}


class Day(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    weekday: Weekday
    pos: int | None = None

    @model_validator(mode="after")
    def _position(self) -> Day:
        if self.pos is not None and self.pos not in _POSITIONS:
            raise ValueError("the position goes from 1 to 5, or -1 to -3 counting from the end")
        return self


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    freq: Freq
    interval: int = Field(default=1, ge=1, le=999)
    by_day: tuple[Day, ...] = ()
    by_month_day: tuple[int, ...] = ()
    by_month: tuple[int, ...] = ()
    count: int | None = Field(default=None, ge=1, le=9999)
    until: date | datetime | None = None

    @field_validator("by_day")
    @classmethod
    def _order_days(cls, value: tuple[Day, ...]) -> tuple[Day, ...]:
        return tuple(_days(value))

    @field_validator("by_month_day")
    @classmethod
    def _order_month_days(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(_month_days(value))

    @field_validator("by_month")
    @classmethod
    def _order_months(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(sorted(value))

    @model_validator(mode="after")
    def _subset(self) -> Rule:
        if self.count is not None and self.until is not None:
            raise ValueError("a rule ends by a count or by a date, not both")
        if isinstance(self.until, datetime) and self.until.tzinfo is not None:
            raise ValueError("UNTIL is wall time, without a zone: the zone goes apart")
        if any(day not in _MONTH_DAYS for day in self.by_month_day):
            raise ValueError("the day of the month goes from 1 to 31, or -1 to -3 from the end")
        if any(month < 1 or month > 12 for month in self.by_month):
            raise ValueError("the month goes from 1 to 12")
        if len(set(self.by_day)) != len(self.by_day):
            raise ValueError("a repeated day")
        if self.by_day and self.by_month_day:
            raise ValueError("either weekdays or days of the month, not both")
        positioned = [day.pos is not None for day in self.by_day]
        if self.freq == "daily" and (self.by_day or self.by_month_day or self.by_month):
            raise ValueError("a daily rule has no days or months")
        if self.freq == "weekly":
            if self.by_month_day or self.by_month:
                raise ValueError("a weekly rule only has weekdays")
            if any(positioned):
                raise ValueError("in a weekly rule the days have no position")
        if self.freq == "monthly" and self.by_month:
            raise ValueError("a monthly rule has no months")
        if self.freq == "monthly" and any(positioned) and not all(positioned):
            raise ValueError("either every day has a position or none does")
        if self.freq == "yearly" and self.by_day and not (self.by_month and all(positioned)):
            raise ValueError("a weekday in a yearly rule goes with its month and position")
        return self


@dataclass(frozen=True)
class Occurrence:
    start: datetime | date
    original: datetime | date
    moved: bool = False


def to_rrule(rule: Rule) -> str:
    parts = [f"FREQ={rule.freq.upper()}"]
    if rule.interval != 1:
        parts.append(f"INTERVAL={rule.interval}")
    if rule.by_month:
        parts.append("BYMONTH=" + ",".join(str(month) for month in sorted(rule.by_month)))
    if rule.by_month_day:
        parts.append("BYMONTHDAY=" + ",".join(str(day) for day in _month_days(rule.by_month_day)))
    if rule.by_day:
        parts.append("BYDAY=" + ",".join(_day_text(day) for day in _days(rule.by_day)))
    if rule.count is not None:
        parts.append(f"COUNT={rule.count}")
    if rule.until is not None:
        parts.append("UNTIL=" + _until_text(rule.until))
    return ";".join(parts)


def parse(text: str) -> Rule:
    body = text.strip().removeprefix("RRULE:")
    fields: dict[str, str] = {}
    for part in body.split(";"):
        if not part:
            continue
        key, sep, value = part.partition("=")
        if not sep:
            raise ValueError(f"parte sin valor: {part!r}")
        fields[key.upper()] = value
    known = {"FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "BYMONTH", "COUNT", "UNTIL", "WKST"}
    unknown = set(fields) - known
    if unknown:
        raise ValueError(f"fuera del subconjunto: {', '.join(sorted(unknown))}")
    if fields.get("WKST", "MO") != "MO":
        raise ValueError("the week starts on Monday")
    freq = fields.get("FREQ", "").lower()
    if freq not in _FREQS:
        raise ValueError(f"frecuencia desconocida: {fields.get('FREQ')!r}")
    return Rule(
        freq=freq,  # type: ignore[arg-type]
        interval=int(fields.get("INTERVAL", "1")),
        by_day=tuple(_parse_day(item) for item in _items(fields.get("BYDAY"))),
        by_month_day=tuple(int(item) for item in _items(fields.get("BYMONTHDAY"))),
        by_month=tuple(int(item) for item in _items(fields.get("BYMONTH"))),
        count=int(fields["COUNT"]) if "COUNT" in fields else None,
        until=_parse_until(fields["UNTIL"]) if "UNTIL" in fields else None,
    )


def _items(value: str | None) -> list[str]:
    return [item for item in (value or "").split(",") if item]


def _parse_day(text: str) -> Day:
    weekday = text[-2:].upper()
    if weekday not in WEEKDAYS:
        raise ValueError(f"unknown day: {text!r}")
    pos = text[:-2]
    return Day(weekday=weekday, pos=int(pos) if pos else None)  # type: ignore[arg-type]


def _day_text(day: Day) -> str:
    return f"{day.pos if day.pos is not None else ''}{day.weekday}"


def _until_text(until: date | datetime) -> str:
    if isinstance(until, datetime):
        return until.strftime("%Y%m%dT%H%M%S")
    return until.strftime("%Y%m%d")


def _parse_until(text: str) -> date | datetime:
    if text.endswith("Z"):
        raise ValueError("UNTIL is wall time, without a zone: the zone goes apart")
    if "T" in text:
        return datetime.strptime(text, "%Y%m%dT%H%M%S")
    return datetime.strptime(text, "%Y%m%d").date()


def _days(days: Iterable[Day]) -> list[Day]:
    return sorted(days, key=lambda d: (WEEKDAYS.index(d.weekday), _pos_key(d.pos)))


def _pos_key(pos: int | None) -> int:
    if pos is None:
        return 0
    return pos if pos > 0 else 10 - pos


def _month_days(days: Iterable[int]) -> list[int]:
    return sorted(days, key=lambda d: d if d > 0 else 100 - d)


def _rrule(rule: Rule, start: date | datetime) -> du.rrule:
    dtstart = _wall(start)
    until: datetime | None = None
    if isinstance(rule.until, datetime):
        until = rule.until
    elif isinstance(rule.until, date):
        until = datetime.combine(rule.until, time(23, 59, 59))
    return du.rrule(
        _FREQS[rule.freq],
        dtstart=dtstart,
        interval=rule.interval,
        wkst=du.MO,
        count=rule.count,
        until=until,
        bymonth=rule.by_month or None,
        bymonthday=rule.by_month_day or None,
        byweekday=[_weekday(day) for day in rule.by_day] or None,
    )


def _weekday(day: Day) -> du.weekday:
    base = getattr(du, day.weekday)
    return base(day.pos) if day.pos is not None else base


def _wall(start: date | datetime) -> datetime:
    if isinstance(start, datetime):
        if start.tzinfo is not None:
            raise ValueError("the start is wall time, without a zone: the zone goes apart")
        return start
    return datetime.combine(start, time())


def _back(value: datetime, like: date | datetime) -> date | datetime:
    return value if isinstance(like, datetime) else value.date()


def _placed(wall: datetime, zone: ZoneInfo) -> datetime:
    return wall.replace(tzinfo=zone).astimezone(UTC).astimezone(zone)


def expand(
    rule: Rule,
    start: date | datetime,
    tz: str,
    window_start: date | datetime,
    window_end: date | datetime,
    *,
    cancelled: Iterable[date | datetime] = (),
    moved: Mapping[date | datetime, date | datetime] | None = None,
) -> list[Occurrence]:
    zone = ZoneInfo(tz)
    all_day = not isinstance(start, datetime)
    series = _rrule(rule, start)
    skip = {_wall(item) for item in cancelled}
    moves = {_wall(original): target for original, target in (moved or {}).items()}

    if all_day:
        if isinstance(window_start, datetime) or isinstance(window_end, datetime):
            raise TypeError("the window of an all-day item is dates")
        low, high = _wall(window_start), _wall(window_end)
        inside = [
            Occurrence(start=wall.date(), original=wall.date())
            for wall in series.between(low, high, inc=True)
            if wall < high and wall not in skip and wall not in moves
        ]
        for original, target in moves.items():
            if original in series and original not in skip and window_start <= target < window_end:
                inside.append(Occurrence(start=target, original=original.date(), moved=True))
        return sorted(inside, key=lambda o: o.start)

    if not isinstance(window_start, datetime) or not isinstance(window_end, datetime):
        raise TypeError("the window of a timed item is instants with a zone")
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("the window goes with a zone")
    low = window_start.astimezone(zone).replace(tzinfo=None) - timedelta(days=1)
    high = window_end.astimezone(zone).replace(tzinfo=None) + timedelta(days=1)
    inside = []
    for wall in series.between(low, high, inc=True):
        if wall in skip or wall in moves:
            continue
        placed = _placed(wall, zone)
        if window_start <= placed < window_end:
            inside.append(Occurrence(start=placed, original=wall))
    for original, target in moves.items():
        if original not in series or original in skip:
            continue
        placed = _placed(_wall(target), zone)
        if window_start <= placed < window_end:
            inside.append(Occurrence(start=placed, original=original, moved=True))
    return sorted(inside, key=lambda o: o.start)


def next_occurrence[S: (date, datetime)](
    rule: Rule, start: S, on_or_after: date | datetime
) -> S | None:
    series = _rrule(rule, start)
    found = series.after(_wall(on_or_after), inc=True)
    return None if found is None else _back(found, start)  # type: ignore[return-value]


def split[S: (date, datetime)](rule: Rule, start: S, at: S) -> tuple[Rule | None, Rule]:
    series = _rrule(rule, start)
    wall = _wall(at)
    if wall not in series:
        raise ValueError(f"{at} is not an occurrence of the series")
    before = 0
    last: datetime | None = None
    for item in series:
        if item >= wall:
            break
        before += 1
        last = item
    if before == 0 or last is None:
        return None, rule
    if rule.count is not None:
        return (
            rule.model_copy(update={"count": before}),
            rule.model_copy(update={"count": rule.count - before}),
        )
    return rule.model_copy(update={"until": _back(last, at)}), rule


def split_exceptions[K: (date, datetime), V](
    exceptions: Mapping[K, V], at: K
) -> tuple[dict[K, V], dict[K, V]]:
    before = {key: value for key, value in exceptions.items() if key < at}
    after = {key: value for key, value in exceptions.items() if key >= at}
    return before, after


Locale = Literal["en", "es"]
_WORDS = Path(__file__).resolve().parent / "i18n"
_WORKWEEK = ("MO", "TU", "WE", "TH", "FR")


@cache
def _catalog(locale: str) -> dict[str, str]:
    path = _WORDS / f"{locale}.json"
    if not path.exists():
        path = _WORDS / "en.json"
    return json.loads(path.read_text(encoding="utf-8"))


class _Say:
    def __init__(self, locale: str) -> None:
        self.words = _catalog(locale)

    def __call__(self, key: str, **values: object) -> str:
        return self.words[key].format(**values)

    def join(self, items: list[str]) -> str:
        if len(items) <= 1:
            return "".join(items)
        return ", ".join(items[:-1]) + self("and") + items[-1]

    def day(self, weekday: Weekday, many: bool = False) -> str:
        return self(f"day.{weekday}.{'many' if many else 'one'}")

    def month(self, month: int) -> str:
        return self(f"month.{month}")

    def ordinal(self, pos: int) -> str:
        return self(f"ordinal.{pos}")

    def month_days(self, days: tuple[int, ...]) -> str:
        ordered = _month_days(days)
        if all(day > 0 for day in ordered):
            if len(ordered) == 1:
                return self("month_day.one", day=ordered[0])
            return self("month_day.many", days=self.join([str(day) for day in ordered]))
        return self.join(
            [
                self("month_day.one", day=day)
                if day > 0
                else self("month_day.from_end", ordinal=self.ordinal(day))
                for day in ordered
            ]
        )

    def positioned(self, days: tuple[Day, ...]) -> str:
        return self.join(
            [
                self("positioned", ordinal=self.ordinal(d.pos), day=self.day(d.weekday))  # type: ignore[arg-type]
                for d in _days(days)
            ]
        )


def describe(rule: Rule, locale: Locale | str = "es") -> str:
    say = _Say(locale)
    key = rule.freq
    parts = [say(f"every.{key}") if rule.interval == 1 else say(f"every_n.{key}", n=rule.interval)]
    weekdays = [day.weekday for day in _days(rule.by_day)]

    if rule.freq == "weekly" and weekdays:
        if rule.interval == 1 and tuple(weekdays) == _WORKWEEK:
            parts = [say("workweek")]
        elif len(weekdays) == 1:
            parts.append(say("weekly.one", day=say.day(weekdays[0])))
        else:
            parts.append(say.join([say.day(day) for day in weekdays]))
    elif rule.freq == "monthly":
        if rule.by_month_day:
            parts.append(say.month_days(rule.by_month_day))
        elif rule.by_day and rule.by_day[0].pos is not None:
            parts.append(say.positioned(rule.by_day))
        elif rule.by_day:
            parts.append(
                say("monthly.weekdays", days=say.join([say.day(d, True) for d in weekdays]))
            )
    elif rule.freq == "yearly" and rule.by_month:
        months = say.join([say.month(month) for month in sorted(rule.by_month)])
        if rule.by_month_day:
            ordered = _month_days(rule.by_month_day)
            if len(ordered) == 1 and ordered[0] > 0:
                parts.append(say("yearly.date", day=ordered[0], month=months))
            else:
                parts.append(
                    say("yearly.of", what=say.month_days(rule.by_month_day), months=months)
                )
        elif rule.by_day:
            parts.append(say("yearly.of", what=say.positioned(rule.by_day), months=months))
        else:
            parts.append(say("yearly.in", months=months))

    if rule.count is not None:
        parts.append(say("count.one") if rule.count == 1 else say("count.many", count=rule.count))
    if rule.until is not None:
        day = rule.until.date() if isinstance(rule.until, datetime) else rule.until
        date_text = say("date", day=day.day, month=say.month(day.month), year=day.year)
        parts.append(say("until", date=date_text))
    return ", ".join(parts)
