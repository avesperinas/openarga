from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from dateutil import rrule as du
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "Day",
    "Freq",
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
            raise ValueError("la posición va de 1 a 5, o -1 a -3 contando desde el final")
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
            raise ValueError("una regla acaba por número de veces o por fecha, no por las dos")
        if isinstance(self.until, datetime) and self.until.tzinfo is not None:
            raise ValueError("UNTIL es hora de pared, sin zona: la zona va aparte")
        if any(day not in _MONTH_DAYS for day in self.by_month_day):
            raise ValueError("el día del mes va de 1 a 31, o -1 a -3 contando desde el final")
        if any(month < 1 or month > 12 for month in self.by_month):
            raise ValueError("el mes va de 1 a 12")
        if len(set(self.by_day)) != len(self.by_day):
            raise ValueError("un día repetido")
        if self.by_day and self.by_month_day:
            raise ValueError("o días de la semana o días del mes, no los dos")
        positioned = [day.pos is not None for day in self.by_day]
        if self.freq == "daily" and (self.by_day or self.by_month_day or self.by_month):
            raise ValueError("una regla diaria no lleva días ni meses")
        if self.freq == "weekly":
            if self.by_month_day or self.by_month:
                raise ValueError("una regla semanal solo lleva días de la semana")
            if any(positioned):
                raise ValueError("en una regla semanal los días no llevan posición")
        if self.freq == "monthly" and self.by_month:
            raise ValueError("una regla mensual no lleva meses")
        if self.freq == "monthly" and any(positioned) and not all(positioned):
            raise ValueError("o todos los días con posición o ninguno")
        if self.freq == "yearly" and self.by_day and not (self.by_month and all(positioned)):
            raise ValueError("un día de la semana en una regla anual va con su mes y su posición")
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
        raise ValueError("la semana empieza el lunes")
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
        raise ValueError(f"día desconocido: {text!r}")
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
        raise ValueError("UNTIL es hora de pared, sin zona: la zona va aparte")
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
            raise ValueError("el inicio es hora de pared, sin zona: la zona va aparte")
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
            raise TypeError("la ventana de algo de todo el día son fechas")
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
        raise TypeError("la ventana de algo con hora son instantes con zona")
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("la ventana va con zona")
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
        raise ValueError(f"{at} no es una ocurrencia de la serie")
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


_DAY_NAMES: dict[Weekday, tuple[str, str]] = {
    "MO": ("lunes", "lunes"),
    "TU": ("martes", "martes"),
    "WE": ("miércoles", "miércoles"),
    "TH": ("jueves", "jueves"),
    "FR": ("viernes", "viernes"),
    "SA": ("sábado", "sábados"),
    "SU": ("domingo", "domingos"),
}
_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
_ORDINALS = {
    1: "primer",
    2: "segundo",
    3: "tercer",
    4: "cuarto",
    5: "quinto",
    -1: "último",
    -2: "penúltimo",
    -3: "antepenúltimo",
}
_UNITS: dict[Freq, tuple[str, str]] = {
    "daily": ("cada día", "días"),
    "weekly": ("cada semana", "semanas"),
    "monthly": ("cada mes", "meses"),
    "yearly": ("cada año", "años"),
}
_WORKWEEK = ("MO", "TU", "WE", "TH", "FR")


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def _month_day_phrases(days: tuple[int, ...]) -> str:
    ordered = _month_days(days)
    if all(day > 0 for day in ordered):
        if len(ordered) == 1:
            return f"el día {ordered[0]}"
        return "los días " + _join([str(day) for day in ordered])
    return _join([f"el día {day}" if day > 0 else f"el {_ORDINALS[day]} día" for day in ordered])


def _positioned(days: tuple[Day, ...]) -> str:
    return _join([f"el {_ORDINALS[d.pos]} {_DAY_NAMES[d.weekday][0]}" for d in _days(days)])  # type: ignore[index]


def describe(rule: Rule) -> str:
    one, many = _UNITS[rule.freq]
    base = one if rule.interval == 1 else f"cada {rule.interval} {many}"
    parts = [base]
    weekdays = [day.weekday for day in _days(rule.by_day)]

    if rule.freq == "weekly" and weekdays:
        if rule.interval == 1 and tuple(weekdays) == _WORKWEEK:
            parts = ["de lunes a viernes"]
        elif len(weekdays) == 1:
            parts.append(f"el {_DAY_NAMES[weekdays[0]][0]}")
        else:
            parts.append(_join([_DAY_NAMES[day][0] for day in weekdays]))
    elif rule.freq == "monthly":
        if rule.by_month_day:
            parts.append(_month_day_phrases(rule.by_month_day))
        elif rule.by_day and rule.by_day[0].pos is not None:
            parts.append(_positioned(rule.by_day))
        elif rule.by_day:
            parts.append("los " + _join([_DAY_NAMES[day][1] for day in weekdays]))
    elif rule.freq == "yearly" and rule.by_month:
        months = _join([_MONTHS[month - 1] for month in sorted(rule.by_month)])
        if rule.by_month_day:
            ordered = _month_days(rule.by_month_day)
            if len(ordered) == 1 and ordered[0] > 0:
                parts.append(f"el {ordered[0]} de {months}")
            else:
                parts.append(f"{_month_day_phrases(rule.by_month_day)} de {months}")
        elif rule.by_day:
            parts.append(f"{_positioned(rule.by_day)} de {months}")
        else:
            parts.append(f"en {months}")

    if rule.count is not None:
        parts.append("una vez" if rule.count == 1 else f"{rule.count} veces")
    if rule.until is not None:
        day = rule.until.date() if isinstance(rule.until, datetime) else rule.until
        parts.append(f"hasta el {day.day} de {_MONTHS[day.month - 1]} de {day.year}")
    return ", ".join(parts)
