from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

METRIC = "metric"
RECORD = "record"

Kind = Literal["deviation", "jump", "trend", "streak", "stall", "goal", "month_pace", "cross"]
Domain = Literal["money", "body", "time", "leisure", "cross"]

DOMAINS: dict[str, Domain] = {
    "money": "money",
    "carrera": "money",
    "vitals": "body",
    "macros": "body",
    "training": "body",
    "recipes": "body",
    "goals": "time",
    "planner": "time",
    "notebook": "time",
    "study": "time",
    "library": "leisure",
    "travel": "leisure",
    "outings": "leisure",
    "arca": "time",
}

HISTORY_DAYS = 460

Z = 2.0
DENSE = 10
JUMP = 0.10
WEEKS = 12
STREAK = 7
STALL_DAYS = 7
MONTH_PACE = 0.25
MONTH_FROM_DAY = 7
CROSS_R = 0.5
CROSS_DELTA = 0.4
CROSS_DAYS = 30
CROSS_KEEP = 3


@dataclass
class Series:
    key: str
    label: str
    unit: str
    kind: str
    points: dict[date, float] = field(default_factory=dict)

    @property
    def app(self) -> str:
        return self.key.split(".", 1)[0]

    @property
    def domain(self) -> Domain:
        return DOMAINS.get(self.app, "cross")

    def until(self, day: date) -> list[tuple[date, float]]:
        return sorted((d, v) for d, v in self.points.items() if d <= day)


@dataclass
class Goal:
    id: str
    title: str
    unit: str | None
    current: float | None
    target: float | None
    expected: float | None
    progress: float | None
    due_on: date | None
    metric: str | None


class Signal(BaseModel):
    id: str
    kind: Kind
    domain: Domain
    text: str
    label: str
    unit: str | None
    value: float
    baseline: float
    baseline_label: str
    day: date
    since: date | None = None
    strength: float
    keys: list[str]


POINTS = text(f"""
    select distinct on (payload->'{METRIC}'->>'key', payload->'{METRIC}'->>'day')
        payload->'{METRIC}'->>'key' as key,
        (payload->'{METRIC}'->>'day')::date as day,
        (payload->'{METRIC}'->>'value')::float8 as value,
        payload->'{METRIC}'->>'label' as label,
        payload->'{METRIC}'->>'unit' as unit,
        payload->'{METRIC}'->>'kind' as kind
    from insights.events
    where payload ? '{METRIC}'
      and (payload->'{METRIC}'->>'day')::date >= :since
    order by payload->'{METRIC}'->>'key', payload->'{METRIC}'->>'day', ts desc, ingested_at desc
""")

GOALS = text(f"""
    select distinct on (payload->'{RECORD}'->>'id', module)
        payload->'{RECORD}' as item
    from insights.events
    where payload ? '{RECORD}' and payload->'{RECORD}'->>'kind' = 'Meta'
    order by payload->'{RECORD}'->>'id', module, ts desc, ingested_at desc
""")


async def series(connection: AsyncConnection, today: date) -> list[Series]:
    rows = await connection.execute(POINTS, {"since": today - timedelta(days=HISTORY_DAYS)})
    found: dict[str, Series] = {}
    for row in rows:
        if not row.key or row.value is None or row.day is None or row.day > today:
            continue
        one = found.get(row.key)
        if one is None:
            one = found[row.key] = Series(row.key, row.label or row.key, row.unit or "", "")
        one.label, one.unit = row.label or one.label, row.unit or one.unit
        one.kind = row.kind if row.kind in ("amount", "peak") else "level"
        one.points[row.day] = float(row.value)
    return list(found.values())


def _number(raw: Any) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _day(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


async def goals(connection: AsyncConnection) -> list[Goal]:
    found = []
    for row in await connection.execute(GOALS):
        item = row.item or {}
        props = item.get("properties") or {}
        if item.get("removed") or props.get("estado") != "activa":
            continue
        if props.get("ritmo") != "por detrás":
            continue
        found.append(
            Goal(
                id=str(item.get("id")),
                title=str(item.get("title") or "Una meta"),
                unit=props.get("unidad"),
                current=_number(props.get("actual")),
                target=_number(props.get("objetivo")),
                expected=_number(props.get("esperado")),
                progress=_number(props.get("progreso")),
                due_on=_day(props.get("hasta")),
                metric=props.get("cifra"),
            )
        )
    return found


UNITS = {
    "EUR": "€",
    "percent": "%",
    "steps": "pasos",
    "count": "",
    "points": "",
}


def unit_of(unit: str | None) -> str:
    return UNITS.get(unit or "", unit or "")


def said(value: float, unit: str | None = None) -> str:
    digits = 0 if abs(value) >= 100 else (1 if abs(value) >= 10 else 2)
    shown = f"{value:,.{digits}f}".replace(",", "·").replace(".", ",").replace("·", ".")
    if "," in shown:
        shown = shown.rstrip("0").rstrip(",")
    shown_unit = unit_of(unit)
    return f"{shown} {shown_unit}".strip()


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def monthly(one: Series) -> bool:
    points = sorted(one.points.items())
    if one.kind != "level" or len(points) < 20:
        return False
    drops = rises = falls = 0
    for (d1, v1), (d2, v2) in zip(points, points[1:], strict=False):
        if (d1.year, d1.month) != (d2.year, d2.month):
            if v2 < v1 * 0.8:
                drops += 1
        elif v2 >= v1:
            rises += 1
        else:
            falls += 1
    return drops >= 2 and falls <= 0.1 * max(rises + falls, 1)


def _daily(one: Series, start: date, end: date) -> list[float]:
    days = (end - start).days + 1
    return [one.points.get(start + timedelta(days=i), 0.0) for i in range(days)]


def _slope(points: list[tuple[date, float]]) -> float | None:
    if len(points) < 2:
        return None
    slopes = [
        (b[1] - a[1]) / (b[0] - a[0]).days
        for i, a in enumerate(points)
        for b in points[i + 1 :]
        if b[0] != a[0]
    ]
    return statistics.median(slopes) if slopes else None


def _correlation(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    try:
        return statistics.correlation(a, b)
    except statistics.StatisticsError:
        return None


def deviation(one: Series, today: date) -> Signal | None:
    if one.kind == "amount":
        return _weekly_deviation(one, today)
    points = one.until(today)
    if not points:
        return None
    last_day, last = points[-1]
    if (today - last_day).days > 7:
        return None
    window = [v for d, v in points[:-1] if (last_day - d).days <= 90]
    if len(window) < DENSE:
        return None
    mean, sd = statistics.fmean(window), statistics.pstdev(window)
    if sd == 0:
        return None
    z = (last - mean) / sd
    if abs(z) < Z:
        return None
    return Signal(
        id=f"deviation:{one.key}",
        kind="deviation",
        domain=one.domain,
        text=(
            f"{one.label}: {said(last, one.unit)} el {last_day:%d/%m}, frente a tu media de 90 "
            f"días de {said(mean, one.unit)} ({z:+.1f} desviaciones)"
        ),
        label=one.label,
        unit=one.unit,
        value=last,
        baseline=round(mean, 2),
        baseline_label="tu media de 90 días",
        day=last_day,
        strength=round(abs(z), 2),
        keys=[one.key],
    )


def _weekly_deviation(one: Series, today: date) -> Signal | None:
    if not one.points:
        return None
    first = min(one.points)
    end = today if today.weekday() == 6 else _monday(today) - timedelta(days=1)
    start = end - timedelta(days=6)
    if start < first:
        return None
    week = sum(_daily(one, start, end))
    before = []
    for i in range(1, WEEKS + 1):
        s = start - timedelta(weeks=i)
        if s < first:
            break
        before.append(sum(_daily(one, s, s + timedelta(days=6))))
    if len(before) < 6 or sum(1 for v in before if v) < 4:
        return None
    mean, sd = statistics.fmean(before), statistics.pstdev(before)
    if sd == 0:
        return None
    z = (week - mean) / sd
    if abs(z) < Z:
        return None
    return Signal(
        id=f"deviation:{one.key}",
        kind="deviation",
        domain=one.domain,
        text=(
            f"{one.label}: {said(week, one.unit)} la semana del {start:%d/%m}, frente a "
            f"{said(mean, one.unit)} de media en tus {len(before)} semanas anteriores "
            f"({z:+.1f} desviaciones)"
        ),
        label=f"{one.label} en la semana",
        unit=one.unit,
        value=round(week, 2),
        baseline=round(mean, 2),
        baseline_label=f"tu media semanal de las {len(before)} anteriores",
        day=end,
        since=start,
        strength=round(abs(z), 2),
        keys=[one.key],
    )


def jump(one: Series, today: date) -> Signal | None:
    if one.kind != "level":
        return None
    points = one.until(today)
    if len(points) < 2:
        return None
    last_day, last = points[-1]
    if (today - last_day).days > 30:
        return None
    if sum(1 for d, _ in points[:-1] if (last_day - d).days <= 90) >= DENSE:
        return None
    previous_day, previous = points[-2]
    if previous == 0:
        return None
    change = (last - previous) / abs(previous)
    if abs(change) < JUMP:
        return None
    return Signal(
        id=f"jump:{one.key}",
        kind="jump",
        domain=one.domain,
        text=(
            f"{one.label}: {said(last, one.unit)} el {last_day:%d/%m/%Y}, frente a "
            f"{said(previous, one.unit)} en la medida anterior ({previous_day:%d/%m/%Y}), "
            f"{change:+.0%}"
        ),
        label=one.label,
        unit=one.unit,
        value=last,
        baseline=previous,
        baseline_label=f"tu medida del {previous_day:%d/%m/%Y}",
        day=last_day,
        since=previous_day,
        strength=round(abs(change), 3),
        keys=[one.key],
    )


def trend(one: Series, today: date) -> Signal | None:
    points = one.until(today)
    if not points or (today - points[-1][0]).days > 7:
        return None
    last = points[-1][0]
    recent = [(d, v) for d, v in points if (last - d).days < 28]
    longer = [(d, v) for d, v in points if (last - d).days < 90]
    if len(recent) < 8 or len(longer) < 20:
        return None
    if one.kind == "amount" and len(longer) < 45:
        return None
    s28, s90 = _slope(recent), _slope(longer)
    if s28 is None or s90 is None:
        return None
    values = [v for _, v in longer]
    sd, mean = statistics.pstdev(values), statistics.fmean(values)
    enough = max(0.5 * sd, 0.01 * abs(mean))
    moved, moved_before = s28 * 28, s90 * 28
    if abs(moved) < enough or enough == 0:
        return None
    turned = moved * moved_before < 0 and abs(s90 * 90) >= enough
    doubled = moved * moved_before > 0 and abs(s28) >= 2 * abs(s90)
    if not (turned or doubled):
        return None
    way = "sube" if moved > 0 else "baja"
    how = "cuando antes iba al revés" if turned else "el doble de rápido que en 90 días"
    return Signal(
        id=f"trend:{one.key}",
        kind="trend",
        domain=one.domain,
        text=(
            f"{one.label} {way}: {said(moved, one.unit)} en 28 días, {how} "
            f"({said(moved_before, one.unit)} cada 28 días a su ritmo de 90)"
        ),
        label=f"{one.label}, cambio en 28 días",
        unit=one.unit,
        value=round(moved, 2),
        baseline=round(moved_before, 2),
        baseline_label="lo que cambiaba en 28 días a tu ritmo de 90",
        day=last,
        since=recent[0][0],
        strength=round(abs(moved) / max(abs(moved_before), enough), 2),
        keys=[one.key],
    )


def streak(one: Series, today: date) -> Signal | None:
    if one.kind != "amount":
        return None
    yesterday = today - timedelta(days=1)
    if one.points.get(yesterday, 0.0) > 0:
        return None
    if yesterday not in one.points and not any(d > yesterday for d in one.points):
        return None
    run, day = 0, yesterday - timedelta(days=1)
    while one.points.get(day, 0.0) > 0:
        run += 1
        day -= timedelta(days=1)
    if run < STREAK:
        return None
    return Signal(
        id=f"streak:{one.key}",
        kind="streak",
        domain=one.domain,
        text=f"{one.label}: llevabas {run} días seguidos y ayer se cortó",
        label=f"{one.label}, días seguidos",
        unit="count",
        value=0,
        baseline=run,
        baseline_label="la racha que llevabas",
        day=yesterday,
        since=day + timedelta(days=1),
        strength=float(run),
        keys=[one.key],
    )


def stall(one: Series, today: date) -> Signal | None:
    counts = one.kind != "amount"
    active = sorted(d for d, v in one.points.items() if d <= today and (v > 0 or counts))
    if len(active) < 2:
        return None
    last = active[-1]
    quiet = (today - last).days
    window = [d for d in active if (last - d).days <= 90]
    if len(window) < 13:
        return None
    gaps = [(b - a).days for a, b in zip(window, window[1:], strict=False)]
    usual = statistics.median(gaps) if gaps else 1
    if quiet < max(STALL_DAYS, 3 * usual):
        return None
    per_week = len(window) / max(((last - window[0]).days + 1) / 7, 1)
    return Signal(
        id=f"stall:{one.app}",
        kind="stall",
        domain=one.domain,
        text=(
            f"{one.label}: nada desde el {last:%d/%m}, hace {quiet} días, cuando solía haber "
            f"{said(per_week)} días con algo a la semana"
        ),
        label=f"días sin {one.label.lower()}",
        unit="count",
        value=quiet,
        baseline=round(usual, 1),
        baseline_label="lo que solía pasar entre un día y el siguiente",
        day=today,
        since=last,
        strength=round(quiet / max(usual, 1), 2),
        keys=[one.key],
    )


def month_pace(one: Series, today: date) -> Signal | None:
    if today.day < MONTH_FROM_DAY or not monthly(one):
        return None
    this = [(d, v) for d, v in one.until(today) if (d.year, d.month) == (today.year, today.month)]
    if not this:
        return None
    day_now, now = this[-1]
    before = []
    year, month = today.year, today.month
    for _ in range(3):
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        same = [
            v
            for d, v in sorted(one.points.items())
            if (d.year, d.month) == (year, month) and d.day <= day_now.day
        ]
        if same:
            before.append(same[-1])
    if len(before) < 2:
        return None
    usual = statistics.fmean(before)
    if usual <= 0:
        return None
    change = (now - usual) / usual
    if abs(change) < MONTH_PACE:
        return None
    way = "por encima" if change > 0 else "por debajo"
    return Signal(
        id=f"month_pace:{one.key}",
        kind="month_pace",
        domain=one.domain,
        text=(
            f"{one.label}: {said(now, one.unit)} a día {day_now.day}, un {abs(change):.0%} {way} "
            f"de los {said(usual, one.unit)} que solías llevar ese día ({len(before)} meses)"
        ),
        label=f"{one.label} a día {day_now.day}",
        unit=one.unit,
        value=now,
        baseline=round(usual, 2),
        baseline_label=f"lo que llevabas a día {day_now.day} en tus {len(before)} meses anteriores",
        day=day_now,
        since=day_now.replace(day=1),
        strength=round(abs(change), 3),
        keys=[one.key],
    )


def goal(one: Goal, today: date) -> Signal:
    has_numbers = one.current is not None and (one.expected is not None or one.target is not None)
    if has_numbers:
        baseline = one.expected if one.expected is not None else one.target
        label = (
            "lo que pedía la meta a estas alturas" if one.expected is not None else "el objetivo"
        )
        value = one.current
    else:
        baseline, label, value = 100.0, "la meta entera", one.progress or 0.0
    due = f", hasta el {one.due_on:%d/%m/%Y}" if one.due_on else ""
    return Signal(
        id=f"goal:{one.id}",
        kind="goal",
        domain="time",
        text=(
            f"Meta «{one.title}»{due}: va por detrás, {said(value or 0, one.unit)} frente a "
            f"{said(baseline or 0, one.unit)} ({label})"
        ),
        label=one.title,
        unit=one.unit,
        value=value or 0.0,
        baseline=baseline or 0.0,
        baseline_label=label,
        day=today,
        strength=1.0,
        keys=[one.metric] if one.metric else [],
    )


def crosses(found: list[Series], today: date) -> list[Signal]:
    usable = [
        one
        for one in found
        if not monthly(one) and sum(1 for d in one.points if (today - d).days < 90) >= CROSS_DAYS
    ]
    out: list[Signal] = []
    for i, a in enumerate(usable):
        for b in usable[i + 1 :]:
            if a.app == b.app:
                continue
            shared = sorted(
                d for d in set(a.points) & set(b.points) if (today - d).days < 365 and d <= today
            )
            recent = [d for d in shared if (today - d).days < 90]
            if len(recent) < CROSS_DAYS or len(shared) < 3 * CROSS_DAYS:
                continue
            r90 = _correlation([a.points[d] for d in recent], [b.points[d] for d in recent])
            r365 = _correlation([a.points[d] for d in shared], [b.points[d] for d in shared])
            if r90 is None or r365 is None or math.isnan(r90) or math.isnan(r365):
                continue
            if abs(r90) < CROSS_R or abs(r90 - r365) < CROSS_DELTA:
                continue
            together = "van juntas" if r90 > 0 else "van al revés"
            out.append(
                Signal(
                    id=f"cross:{a.key}|{b.key}",
                    kind="cross",
                    domain="cross",
                    text=(
                        f"{a.label} y {b.label} {together} estos 90 días (r = {r90:.2f}), "
                        f"cuando en el año la relación era {r365:.2f}"
                    ),
                    label=f"relación entre {a.label.lower()} y {b.label.lower()}",
                    unit=None,
                    value=round(r90, 2),
                    baseline=round(r365, 2),
                    baseline_label="la misma relación en el último año",
                    day=recent[-1],
                    since=recent[0],
                    strength=round(abs(r90 - r365), 2),
                    keys=[a.key, b.key],
                )
            )
    out.sort(key=lambda one: one.strength, reverse=True)
    return out[:CROSS_KEEP]


PER_SERIES = (deviation, jump, trend, streak, month_pace)


def detect(
    found: list[Series], behind: list[Goal], today: date, *, with_crosses: bool = True
) -> list[Signal]:
    out: list[Signal] = []
    stalls: dict[str, tuple[int, Signal]] = {}
    for one in found:
        cumulative = monthly(one)
        for check in PER_SERIES:
            if cumulative and check in (deviation, trend, jump):
                continue
            signal = check(one, today)
            if signal is not None:
                out.append(signal)
        stopped = stall(one, today)
        if stopped is not None and len(one.points) > stalls.get(one.app, (0, stopped))[0]:
            stalls[one.app] = (len(one.points), stopped)
    out += [signal for _, signal in stalls.values()]
    out += [goal(one, today) for one in behind]
    if with_crosses:
        out += crosses(found, today)
    order = {kind: i for i, kind in enumerate(Kind.__args__)}
    out.sort(key=lambda one: (order[one.kind], -one.strength))
    return out


def period(found: list[Series], behind: list[Goal], since: date, until: date) -> list[Signal]:
    kept: dict[str, Signal] = {}
    day = since
    while day <= until:
        for one in detect(found, [], day, with_crosses=False):
            kept[one.id] = one
        day += timedelta(days=1)
    for one in [goal(g, until) for g in behind] + crosses(found, until):
        kept[one.id] = one
    order = {kind: i for i, kind in enumerate(Kind.__args__)}
    return sorted(kept.values(), key=lambda one: (order[one.kind], -one.strength))


async def read(connection: AsyncConnection, since: date, until: date) -> list[Signal]:
    found = await series(connection, until)
    behind = await goals(connection)
    return period(found, behind, since, until)
