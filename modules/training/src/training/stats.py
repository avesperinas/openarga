from __future__ import annotations

import asyncio
import math
import threading
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import current_user
from training import bodyweight, strength
from training.strength import epley

__all__ = ["epley"]

Period = Literal["4w", "3m", "1y", "all"]

SPANS: dict[str, timedelta | None] = {
    "4w": timedelta(weeks=4),
    "3m": timedelta(days=91),
    "1y": timedelta(days=365),
    "all": None,
}

EFFECTIVE_LOW = 10
EFFECTIVE_HIGH = 20

RELIABLE_REPS = 10

MIN_WEEKS = 2


def starts_on(period: Period, today: date, first: date | None) -> date:
    span = SPANS[period]
    if span is None:
        return first or today
    return today - span


def direction_of(delta: float) -> Literal["up", "flat", "down"]:
    return "up" if delta > 1 else "down" if delta < -1 else "flat"


class Trend(BaseModel):
    day: date
    value: float


class Index(BaseModel):
    value: float | None
    delta: float | None
    direction: Literal["up", "flat", "down"] | None
    muscles: int
    trend: list[Trend]


class Frequency(BaseModel):
    done: int
    goal: int
    average: float
    streak: int


class MuscleSummary(BaseModel):
    muscle: str
    name: str
    region: str
    sets: float
    band: Literal["low", "ok", "high"]
    value: float | None
    delta: float | None
    direction: Literal["up", "flat", "down"] | None
    trend: list[Trend]
    last_day: date | None
    current: str | None
    excluded: int


class Mover(BaseModel):
    variant_id: str
    gym_id: str | None
    gym: str | None
    exercise: str
    variant: str
    e1rm: float
    delta: float
    sessions: int
    without_pr: int


class Stats(BaseModel):
    period: Period
    since: date
    until: date
    sessions: int
    index: Index
    frequency: Frequency
    muscles: list[MuscleSummary]
    movers: list[Mover]
    excluded: int
    bodyweight: float | None


ENTRIES = text("""
    select cast(se.id as text)          as id,
           cast(se.session_id as text)  as session_id,
           cast(se.variant_id as text)  as variant_id,
           cast(s.gym_id as text)       as gym_id,
           s.day,
           e.load_type,
           e.bodyweight_factor,
           v.index_weight,
           pm.muscle_id                 as muscle,
           l.reps,
           l.weight,
           l.added_load,
           l.completed
    from training.training_session_exercise se
    join training.training_session s on s.id = se.session_id
    join training.training_variant v on v.id = se.variant_id
    join training.training_exercise e on e.id = v.exercise_id
    left join training.training_exercise_muscle pm
           on pm.exercise_id = e.id and pm.contribution = 1.0
    join training.training_set_log l on l.session_exercise_id = se.id
    where s.ended_at is not null and s.day <= :until
    order by se.id, l.number
""")


MARKS = text("""
    select cast(id as text) as id, cast(variant_id as text) as variant_id,
           cast(gym_id as text) as gym_id, day, kind
    from training.training_series_mark
""")

VERDICTS = text("""
    select cast(session_exercise_id as text) as id, verdict from training.training_point_review
""")

NAMES = text("""
    select cast(v.id as text) as variant_id, e.name as exercise, v.name as variant,
           v.implement, v.min_increment, e.load_type, pm.muscle_id as muscle
    from training.training_variant v
    join training.training_exercise e on e.id = v.exercise_id
    left join training.training_exercise_muscle pm on pm.exercise_id = e.id and pm.contribution = 1.0
""")

GYMS = text("select cast(id as text) as id, name from training.training_gym")

MUSCLES = text("select id, name, region from training.training_muscle order by region, name")

VOLUME = text("""
    select pm.muscle_id as muscle, count(*) as sets
    from training.training_session_exercise se
    join training.training_session s on s.id = se.session_id
    join training.training_set_log l on l.session_exercise_id = se.id
    join training.training_variant v on v.id = se.variant_id
    join training.training_exercise_muscle pm
      on pm.exercise_id = v.exercise_id and pm.contribution = 1.0
    where l.completed and s.ended_at is not null and s.day >= :since and s.day <= :until
    group by pm.muscle_id
""")

DAYS = text("""
    select s.day
    from training.training_session s
    where s.ended_at is not null and s.day >= :since and s.day <= :until
    order by s.day
""")

FIRST_DAY = text("select min(day) as day from training.training_session where ended_at is not null")


@dataclass(frozen=True)
class Name:
    exercise: str
    variant: str
    implement: str
    min_increment: float
    load_type: str
    muscle: str | None

    @property
    def label(self) -> str:
        if self.variant.lower().startswith(self.exercise.lower()):
            return self.variant
        return f"{self.exercise} · {self.variant}"


@dataclass
class Analysis:
    today: date
    entries: dict[str, strength.Entry]
    series: list[strength.Series]
    names: dict[str, Name]
    gyms: dict[str, str]
    marks: list[strength.Mark]
    bodyweight: float | None
    _curves: dict[str, strength.Curve | None] = field(default_factory=dict)

    def of_muscle(self, muscle: str) -> list[strength.Series]:
        return [serie for serie in self.series if serie.points[0].muscle == muscle]

    def curve(self, muscle: str) -> strength.Curve | None:
        if muscle not in self._curves:
            self._curves[muscle] = strength.fit(self.of_muscle(muscle), self.today)
        return self._curves[muscle]

    def gym(self, gym_id: str | None) -> str | None:
        return self.gyms.get(gym_id) if gym_id else None


_KEPT: OrderedDict[tuple, Analysis] = OrderedDict()
_KEPT_LOCK = threading.Lock()
_KEEP = 8


def _kept(key: tuple) -> Analysis | None:
    with _KEPT_LOCK:
        found = _KEPT.get(key)
        if found is not None:
            _KEPT.move_to_end(key)
        return found


def _keep(key: tuple, analysis: Analysis) -> None:
    with _KEPT_LOCK:
        for old in [old for old in _KEPT if old[0] == key[0]]:
            del _KEPT[old]
        _KEPT[key] = analysis
        while len(_KEPT) > _KEEP:
            _KEPT.popitem(last=False)


async def analyse(connection: AsyncConnection, today: date) -> Analysis:
    rows = (await connection.execute(ENTRIES, {"until": today})).all()
    weight_rows = (await connection.execute(bodyweight.DAYS)).all()
    mark_rows = (await connection.execute(MARKS)).all()
    verdict_rows = (await connection.execute(VERDICTS)).all()
    name_rows = (await connection.execute(NAMES)).all()
    gym_rows = (await connection.execute(GYMS)).all()
    key = (
        current_user.get(),
        today,
        hash(
            (
                tuple(rows),
                tuple(weight_rows),
                tuple(mark_rows),
                tuple(verdict_rows),
                tuple(name_rows),
                tuple(gym_rows),
            )
        ),
    )
    found = _kept(key)
    if found is not None:
        return found

    grouped: dict[str, list[strength.LoggedSet]] = defaultdict(list)
    heads = {}
    for row in rows:
        grouped[row.id].append(
            strength.LoggedSet(
                reps=row.reps,
                weight=float(row.weight) if row.weight is not None else None,
                added_load=float(row.added_load) if row.added_load is not None else None,
                completed=row.completed,
            )
        )
        heads.setdefault(row.id, row)
    entries = {
        key: strength.Entry(
            id=key,
            session_id=head.session_id,
            variant_id=head.variant_id,
            gym_id=head.gym_id,
            day=head.day,
            muscle=head.muscle,
            index_weight=head.index_weight,
            load_type=head.load_type,
            bodyweight_factor=float(head.bodyweight_factor)
            if head.bodyweight_factor is not None
            else None,
            sets=tuple(grouped[key]),
        )
        for key, head in heads.items()
    }
    weights = strength.Bodyweights((row.day, float(row.kg)) for row in weight_rows)
    marks = [
        strength.Mark(
            id=row.id, variant_id=row.variant_id, gym_id=row.gym_id, day=row.day, kind=row.kind
        )
        for row in mark_rows
    ]
    verdicts = {row.id: row.verdict for row in verdict_rows}
    names = {
        row.variant_id: Name(
            exercise=row.exercise,
            variant=row.variant,
            implement=row.implement,
            min_increment=float(row.min_increment),
            load_type=row.load_type,
            muscle=row.muscle,
        )
        for row in name_rows
    }
    gyms = {row.id: row.name for row in gym_rows}
    series = await asyncio.to_thread(
        lambda: strength.build(strength.points_of(entries.values(), weights), marks, verdicts)
    )
    analysis = Analysis(
        today=today,
        entries=entries,
        series=series,
        names=names,
        gyms=gyms,
        marks=marks,
        bodyweight=weights.on(today),
    )
    _keep(key, analysis)
    return analysis


async def warm(connection: AsyncConnection, today: date) -> None:
    analysis = await analyse(connection, today)
    muscles = {entry.muscle for entry in analysis.entries.values() if entry.muscle}
    await asyncio.to_thread(lambda: [analysis.curve(muscle) for muscle in muscles])


@dataclass(frozen=True)
class Strength:
    value: float
    delta: float
    direction: Literal["up", "flat", "down"]
    trend: list[Trend]


def mondays(since: date, until: date) -> list[date]:
    first = strength.monday(since)
    return [first + timedelta(weeks=n) for n in range((until - first).days // 7 + 1)]


def muscle_strength(analysis: Analysis, muscle: str, since: date, until: date) -> Strength | None:
    weeks = {
        strength.monday(point.day)
        for serie in analysis.of_muscle(muscle)
        for point in serie.counted
        if since <= point.day <= until
    }
    curve = analysis.curve(muscle)
    if len(weeks) < MIN_WEEKS or curve is None:
        return None
    base = curve.at(since)
    trend = [
        Trend(day=monday, value=round(100 * math.exp(curve.at(monday) - base), 1))
        for monday in mondays(since, until)
    ]
    value = round(100 * math.exp(curve.at(until) - base), 1)
    delta = round(value - 100, 1)
    return Strength(value=value, delta=delta, direction=direction_of(delta), trend=trend)


def overall(found: list[Strength]) -> Index:
    if not found:
        return Index(value=None, delta=None, direction=None, muscles=0, trend=[])
    value = round(sum(item.value for item in found) / len(found), 1)
    delta = round(value - 100, 1)
    length = min(len(item.trend) for item in found)
    trend = [
        Trend(
            day=found[0].trend[index].day,
            value=round(sum(item.trend[index].value for item in found) / len(found), 1),
        )
        for index in range(length)
    ]
    return Index(
        value=value, delta=delta, direction=direction_of(delta), muscles=len(found), trend=trend
    )


WINDOW = timedelta(days=21)


@dataclass(frozen=True)
class Best:
    variant_id: str
    day: date
    reps: int
    load: float
    e1rm: float
    weight: int


class VariantIndex(BaseModel):
    value: float | None
    delta: float | None
    direction: Literal["up", "flat", "down"] | None
    variants: int
    trend: list[Trend]


def _best_in(bests: list[Best], until: date, window: timedelta = WINDOW) -> float | None:
    inside = [b.e1rm for b in bests if until - window <= b.day <= until]
    return max(inside) if inside else None


def performance_index(bests: list[Best], since: date, until: date) -> VariantIndex:
    by_variant: dict[str, list[Best]] = defaultdict(list)
    for best in bests:
        by_variant[best.variant_id].append(best)

    ratios: list[tuple[float, int]] = []
    for entries in by_variant.values():
        reference = _best_in(entries, since + WINDOW)
        current = _best_in(entries, until)
        if reference and current:
            ratios.append((current / reference, entries[0].weight))

    if not ratios:
        return VariantIndex(value=None, delta=None, direction=None, variants=0, trend=[])

    total = sum(weight for _, weight in ratios)
    value = round(sum(ratio * weight for ratio, weight in ratios) / total * 100, 1)
    delta = round(value - 100, 1)

    trend: list[Trend] = []
    day = since + WINDOW
    while day <= until:
        points = [
            (_best_in(entries, day), _best_in(entries, since + WINDOW), entries[0].weight)
            for entries in by_variant.values()
        ]
        usable = [(now / ref, weight) for now, ref, weight in points if now and ref]
        if usable:
            share = sum(weight for _, weight in usable)
            trend.append(
                Trend(day=day, value=round(sum(r * w for r, w in usable) / share * 100, 1))
            )
        day += timedelta(days=7)

    return VariantIndex(
        value=value,
        delta=delta,
        direction=direction_of(delta),
        variants=len(ratios),
        trend=trend,
    )


def frequency(days: list[date], goal: int, today: date) -> Frequency:
    monday = today - timedelta(days=today.weekday())
    weeks: dict[date, int] = defaultdict(int)
    for day in days:
        weeks[day - timedelta(days=day.weekday())] += 1

    done = weeks.get(monday, 0)
    last_four = [weeks.get(monday - timedelta(weeks=n), 0) for n in range(1, 5)]
    average = round(sum(last_four) / 4, 1) if last_four else 0.0

    streak = 0
    week = monday - timedelta(weeks=1)
    while weeks.get(week, 0) >= goal:
        streak += 1
        week -= timedelta(weeks=1)

    return Frequency(done=done, goal=goal, average=average, streak=streak)


def per_week(sets: float, since: date, until: date) -> float:
    weeks = max((until - since).days / 7, 1)
    return round(sets / weeks, 1)


def band(sets: float) -> Literal["low", "ok", "high"]:
    if sets < EFFECTIVE_LOW:
        return "low"
    return "high" if sets > EFFECTIVE_HIGH else "ok"


def movers(analysis: Analysis, since: date, until: date) -> list[Mover]:
    out: dict[tuple[str, str | None], Mover] = {}
    for serie in sorted(analysis.series, key=lambda serie: serie.since):
        inside = [point for point in serie.counted if since <= point.day <= until]
        name = analysis.names.get(serie.variant_id)
        if len(inside) < 2 or name is None:
            continue
        first, last = inside[0], inside[-1]
        peak = max(inside, key=lambda point: point.e1rm)
        out[(serie.variant_id, serie.gym_id)] = Mover(
            variant_id=serie.variant_id,
            gym_id=serie.gym_id,
            gym=analysis.gym(serie.gym_id),
            exercise=name.exercise,
            variant=name.variant,
            e1rm=round(last.e1rm, 1),
            delta=round((last.e1rm / first.e1rm - 1) * 100, 1),
            sessions=len(inside),
            without_pr=sum(1 for point in inside if point.day > peak.day),
        )
    return sorted(out.values(), key=lambda mover: mover.delta, reverse=True)


async def read(connection: AsyncConnection, period: Period, today: date, goal: int) -> Stats:
    first = await connection.scalar(FIRST_DAY)
    since = starts_on(period, today, first)
    window = {"since": since, "until": today}

    analysis = await analyse(connection, today)
    days = [row.day for row in (await connection.execute(DAYS, window)).all()]
    volume = {row.muscle: int(row.sets) for row in (await connection.execute(VOLUME, window)).all()}
    rows = (await connection.execute(MUSCLES)).all()
    return await asyncio.to_thread(
        summarise, analysis, rows, days, volume, period, since, today, goal
    )


def summarise(
    analysis: Analysis,
    rows: list,
    days: list[date],
    volume: dict[str, int],
    period: Period,
    since: date,
    today: date,
    goal: int,
) -> Stats:
    last_of: dict[str, strength.Entry] = {}
    for entry in analysis.entries.values():
        if entry.muscle and (entry.muscle not in last_of or entry.day > last_of[entry.muscle].day):
            last_of[entry.muscle] = entry

    muscles: list[MuscleSummary] = []
    found: list[Strength] = []
    for row in rows:
        measured = muscle_strength(analysis, row.id, since, today)
        if measured:
            found.append(measured)
        points = [point for serie in analysis.of_muscle(row.id) for point in serie.points]
        latest = last_of.get(row.id)
        name = analysis.names.get(latest.variant_id) if latest else None
        weekly = per_week(volume.get(row.id, 0), since, today)
        muscles.append(
            MuscleSummary(
                muscle=row.id,
                name=row.name,
                region=row.region,
                sets=weekly,
                band=band(weekly),
                value=measured.value if measured else None,
                delta=measured.delta if measured else None,
                direction=measured.direction if measured else None,
                trend=measured.trend if measured else [],
                last_day=latest.day if latest else None,
                current=name.label if name else None,
                excluded=sum(
                    1 for point in points if not point.counted and since <= point.day <= today
                ),
            )
        )

    return Stats(
        period=period,
        since=since,
        until=today,
        sessions=len(days),
        index=overall(found),
        frequency=frequency(days, goal, today),
        muscles=muscles,
        movers=movers(analysis, since, today),
        excluded=sum(muscle.excluded for muscle in muscles),
        bodyweight=analysis.bodyweight,
    )


class ExerciseHistory(BaseModel):
    variant_id: str
    exercise: str
    variant: str
    gyms: list[str]
    first_day: date
    last_day: date
    sessions: int
    excluded: int
    best: float | None
    last: float | None
    delta: float | None


class MuscleStats(BaseModel):
    muscle: str
    name: str
    region: str
    since: date
    until: date
    value: float | None
    delta: float | None
    direction: Literal["up", "flat", "down"] | None
    trend: list[Trend]
    sets: float
    band: Literal["low", "ok", "high"]
    last_day: date | None
    changes: list[date]
    exercises: list[ExerciseHistory]


def history(analysis: Analysis, muscle: str) -> list[ExerciseHistory]:
    entries: dict[str, list[strength.Entry]] = defaultdict(list)
    for entry in analysis.entries.values():
        if entry.muscle == muscle:
            entries[entry.variant_id].append(entry)
    series: dict[str, list[strength.Series]] = defaultdict(list)
    for serie in analysis.of_muscle(muscle):
        series[serie.variant_id].append(serie)
    out = []
    for variant_id, done in entries.items():
        name = analysis.names.get(variant_id)
        if name is None:
            continue
        done.sort(key=lambda entry: entry.day)
        found = sorted(series.get(variant_id, []), key=lambda serie: serie.until)
        recent = found[-1].counted if found else []
        gyms: list[str] = []
        for entry in reversed(done):
            gym = analysis.gym(entry.gym_id) or "Sin centro"
            if gym not in gyms:
                gyms.append(gym)
        out.append(
            ExerciseHistory(
                variant_id=variant_id,
                exercise=name.exercise,
                variant=name.variant,
                gyms=gyms,
                first_day=done[0].day,
                last_day=done[-1].day,
                sessions=len(done),
                excluded=sum(1 for serie in found for point in serie.points if not point.counted),
                best=round(max(point.e1rm for point in recent), 1) if recent else None,
                last=round(recent[-1].e1rm, 1) if recent else None,
                delta=round((recent[-1].e1rm / recent[0].e1rm - 1) * 100, 1)
                if len(recent) >= 2
                else None,
            )
        )
    return sorted(out, key=lambda item: item.last_day, reverse=True)


def changes_of(own: list[strength.Series], since: date, until: date) -> list[date]:
    days: set[date] = set()
    by_variant: dict[str, list[strength.Point]] = defaultdict(list)
    for serie in own:
        if serie.start in ("mark", "detected"):
            days.add(serie.since)
        by_variant[serie.variant_id].extend(serie.points)
    for points in by_variant.values():
        points.sort(key=lambda point: point.day)
        for previous, point in zip(points, points[1:], strict=False):
            if previous.gym_id != point.gym_id:
                days.add(point.day)
    return sorted(day for day in days if since < day <= until)


async def read_muscle(
    connection: AsyncConnection, muscle: str, period: Period, today: date
) -> MuscleStats | None:
    found = (
        await connection.execute(
            text("select id, name, region from training.training_muscle where id = :id"),
            {"id": muscle},
        )
    ).first()
    if found is None:
        return None
    first = await connection.scalar(FIRST_DAY)
    since = starts_on(period, today, first)
    window = {"since": since, "until": today}
    analysis = await analyse(connection, today)
    measured = muscle_strength(analysis, muscle, since, today)
    volume = {row.muscle: int(row.sets) for row in (await connection.execute(VOLUME, window)).all()}
    weekly = per_week(volume.get(muscle, 0), since, today)
    days = [entry.day for entry in analysis.entries.values() if entry.muscle == muscle]
    return MuscleStats(
        muscle=found.id,
        name=found.name,
        region=found.region,
        since=since,
        until=today,
        value=measured.value if measured else None,
        delta=measured.delta if measured else None,
        direction=measured.direction if measured else None,
        trend=measured.trend if measured else [],
        sets=weekly,
        band=band(weekly),
        last_day=max(days, default=None),
        changes=changes_of(analysis.of_muscle(muscle), since, today),
        exercises=history(analysis, muscle),
    )


RANGES: tuple[tuple[str, int, int], ...] = (("1-5", 1, 5), ("6-10", 6, 10), ("11+", 11, 200))


class Point(BaseModel):
    id: str
    session_id: str
    day: date
    reps: int
    load: float
    e1rm: float
    reliable: bool
    status: strength.Status
    reference: float | None
    verdict: strength.Verdict | None


class Record(BaseModel):
    range: str
    load: float
    reps: int
    day: date
    reliable: bool


class Segment(BaseModel):
    since: date
    until: date
    start: strength.Start
    jump: float | None
    mark_id: str | None


class MarkOut(BaseModel):
    id: str
    day: date
    kind: Literal["split", "join"]


class Machine(BaseModel):
    gym_id: str | None
    gym: str | None
    first_day: date
    last_day: date
    points: list[Point]
    segments: list[Segment]
    marks: list[MarkOut]
    best: Point | None
    records: list[Record]
    without_pr: int
    excluded: int


class VariantStats(BaseModel):
    variant_id: str
    exercise: str
    variant: str
    implement: str
    load_type: str
    muscle: str | None
    min_increment: float
    since: date
    until: date
    bodyweight: float | None
    machines: list[Machine]
    notes: list[dict[str, str]] = []


def records(rows: list[tuple[date, int, float]]) -> list[Record]:
    out: list[Record] = []
    for label, low, high in RANGES:
        inside = [row for row in rows if low <= row[1] <= high]
        if not inside:
            continue
        day, reps, load = max(inside, key=lambda row: row[2])
        out.append(
            Record(range=label, load=load, reps=reps, day=day, reliable=reps <= RELIABLE_REPS)
        )
    return out


def _point(point: strength.Point) -> Point:
    return Point(
        id=point.id,
        session_id=point.session_id,
        day=point.day,
        reps=point.reps,
        load=round(point.load, 2),
        e1rm=round(point.e1rm, 1),
        reliable=point.reps <= RELIABLE_REPS,
        status=point.status,
        reference=round(point.reference, 1) if point.reference else None,
        verdict=point.verdict,
    )


def _level(points: list[strength.Point]) -> float | None:
    values = sorted(point.e1rm for point in points)
    return values[len(values) // 2] if values else None


def machine(analysis: Analysis, found: list[strength.Series], since: date, until: date) -> Machine:
    found.sort(key=lambda serie: serie.since)
    gym_id, variant_id = found[0].gym_id, found[0].variant_id
    marks = [
        mark for mark in analysis.marks if (mark.variant_id, mark.gym_id) == (variant_id, gym_id)
    ]
    segments = []
    for index, serie in enumerate(found):
        jump = mark_id = None
        if index > 0 and serie.start == "detected":
            before, after = _level(found[index - 1].counted[-4:]), _level(serie.counted[:4])
            if before and after:
                jump = round((after / before - 1) * 100, 1)
        if index > 0 and serie.start == "mark":
            mark_id = next(
                (
                    mark.id
                    for mark in marks
                    if mark.kind == "split" and found[index - 1].until < mark.day <= serie.since
                ),
                None,
            )
        segments.append(
            Segment(
                since=serie.since, until=serie.until, start=serie.start, jump=jump, mark_id=mark_id
            )
        )

    inside = [point for serie in found for point in serie.points if since <= point.day <= until]
    counted = [point for point in inside if point.counted]
    best = max(counted, key=lambda point: point.e1rm, default=None)
    rows = [
        (point.day, logged.reps, float(logged.weight or logged.added_load or 0))
        for point in counted
        for logged in analysis.entries[point.id].sets
        if logged.completed and logged.reps and (logged.weight or logged.added_load)
    ]
    return Machine(
        gym_id=gym_id,
        gym=analysis.gym(gym_id),
        first_day=found[0].since,
        last_day=found[-1].until,
        points=[_point(point) for point in inside],
        segments=segments,
        marks=[MarkOut(id=mark.id, day=mark.day, kind=mark.kind) for mark in marks],
        best=_point(best) if best else None,
        records=records(rows),
        without_pr=sum(1 for point in counted if best and point.day > best.day),
        excluded=len(inside) - len(counted),
    )


async def read_variant(
    connection: AsyncConnection, variant_id: str, period: Period, today: date
) -> VariantStats | None:
    analysis = await analyse(connection, today)
    name = analysis.names.get(variant_id)
    if name is None:
        return None
    first = await connection.scalar(FIRST_DAY)
    since = starts_on(period, today, first)
    by_gym: dict[str | None, list[strength.Series]] = defaultdict(list)
    for serie in analysis.series:
        if serie.variant_id == variant_id:
            by_gym[serie.gym_id].append(serie)
    machines = [machine(analysis, found, since, today) for found in by_gym.values()]
    return VariantStats(
        variant_id=variant_id,
        exercise=name.exercise,
        variant=name.variant,
        implement=name.implement,
        load_type=name.load_type,
        muscle=name.muscle,
        min_increment=name.min_increment,
        since=since,
        until=today,
        bodyweight=analysis.bodyweight,
        machines=sorted(machines, key=lambda item: item.last_day, reverse=True),
    )


class VerdictIn(BaseModel):
    verdict: strength.Verdict


async def set_verdict(connection: AsyncConnection, point_id: str, request: VerdictIn) -> bool:
    exists = await connection.scalar(
        text("select 1 from training.training_session_exercise where id = cast(:id as uuid)"),
        {"id": point_id},
    )
    if not exists:
        return False
    await connection.execute(
        text(
            "insert into training.training_point_review (session_exercise_id, verdict) "
            "values (cast(:id as uuid), :verdict) "
            "on conflict (user_id, session_exercise_id) do update "
            "set verdict = excluded.verdict, created_at = now()"
        ),
        {"id": point_id, "verdict": request.verdict},
    )
    return True


async def clear_verdict(connection: AsyncConnection, point_id: str) -> None:
    await connection.execute(
        text(
            "delete from training.training_point_review where session_exercise_id = cast(:id as uuid)"
        ),
        {"id": point_id},
    )


class MarkIn(BaseModel):
    variant_id: str
    gym_id: str | None = None
    day: date
    kind: Literal["split", "join"]


async def add_mark(connection: AsyncConnection, request: MarkIn) -> str | None:
    exists = await connection.scalar(
        text("select 1 from training.training_variant where id = cast(:id as uuid)"),
        {"id": request.variant_id},
    )
    if not exists:
        return None
    found = await connection.scalar(
        text(
            "insert into training.training_series_mark (variant_id, gym_id, day, kind) "
            "values (cast(:variant as uuid), cast(:gym as uuid), :day, :kind) "
            "on conflict (user_id, variant_id, gym_id, day) do update set kind = excluded.kind "
            "returning id"
        ),
        {
            "variant": request.variant_id,
            "gym": request.gym_id,
            "day": request.day,
            "kind": request.kind,
        },
    )
    return str(found)


async def remove_mark(connection: AsyncConnection, mark_id: str) -> None:
    await connection.execute(
        text("delete from training.training_series_mark where id = cast(:id as uuid)"),
        {"id": mark_id},
    )
