from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from statistics import median
from typing import Literal

import numpy as np

MAX_REPS = 15

WARM_UP = 0.6

OUTLIER = 0.30
NEIGHBOURS = 6
REACH = timedelta(days=120)

STEP = 0.35
STEADY = 0.20
STEP_SIDE = 4
LONG_BREAK = timedelta(days=42)

CALIBRATION = timedelta(days=21)

SMOOTHING = 8.0
ROBUST = math.log(1.15)

Status = Literal["counted", "high", "low", "excluded"]
Verdict = Literal["counted", "excluded"]


def epley(reps: int, load: float) -> float:
    return load * (1 + reps / 30)


@dataclass(frozen=True)
class LoggedSet:
    reps: int | None
    weight: float | None
    added_load: float | None
    completed: bool = True


@dataclass(frozen=True)
class Entry:
    id: str
    session_id: str
    variant_id: str
    gym_id: str | None
    day: date
    muscle: str | None
    index_weight: int
    load_type: str
    bodyweight_factor: float | None
    sets: tuple[LoggedSet, ...]


def total_load(entry: Entry, logged: LoggedSet, bodyweight: float | None) -> float | None:
    if entry.load_type == "external":
        return logged.weight if logged.weight else None
    if bodyweight is None:
        return None
    extra = logged.added_load if logged.added_load is not None else (logged.weight or 0)
    return bodyweight * (entry.bodyweight_factor or 1.0) + extra


@dataclass(frozen=True)
class Best:
    reps: int
    load: float
    e1rm: float


def best_set(entry: Entry, bodyweight: float | None) -> Best | None:
    usable = []
    for logged in entry.sets:
        if not logged.completed or logged.reps is None or not 1 <= logged.reps <= MAX_REPS:
            continue
        load = total_load(entry, logged, bodyweight)
        if load is None or load <= 0:
            continue
        usable.append((logged.reps, load))
    if not usable:
        return None
    heaviest = max(load for _, load in usable)
    working = [(reps, load) for reps, load in usable if load >= heaviest * WARM_UP]
    reps, load = max(working, key=lambda pair: epley(*pair))
    return Best(reps=reps, load=load, e1rm=epley(reps, load))


@dataclass(frozen=True)
class Point:
    id: str
    session_id: str
    variant_id: str
    gym_id: str | None
    day: date
    muscle: str | None
    index_weight: int
    reps: int
    load: float
    e1rm: float
    status: Status = "counted"
    reference: float | None = None
    verdict: Verdict | None = None

    @property
    def counted(self) -> bool:
        return self.status == "counted"


class Bodyweights:
    def __init__(self, entries: Iterable[tuple[date, float]]):
        self.entries = sorted(entries)

    def on(self, day: date) -> float | None:
        if not self.entries:
            return None
        before = [kg for when, kg in self.entries if when <= day]
        return before[-1] if before else self.entries[0][1]


def points_of(entries: Iterable[Entry], bodyweights: Bodyweights) -> list[Point]:
    out = []
    for entry in entries:
        best = best_set(entry, bodyweights.on(entry.day))
        if best is None:
            continue
        out.append(
            Point(
                id=entry.id,
                session_id=entry.session_id,
                variant_id=entry.variant_id,
                gym_id=entry.gym_id,
                day=entry.day,
                muscle=entry.muscle,
                index_weight=entry.index_weight,
                reps=best.reps,
                load=best.load,
                e1rm=best.e1rm,
            )
        )
    return out


@dataclass(frozen=True)
class Mark:
    id: str
    variant_id: str
    gym_id: str | None
    day: date
    kind: Literal["split", "join"]


Start = Literal["first", "mark", "detected"]


@dataclass
class Series:
    variant_id: str
    gym_id: str | None
    points: list[Point]
    start: Start = "first"

    @property
    def since(self) -> date:
        return self.points[0].day

    @property
    def until(self) -> date:
        return self.points[-1].day

    @property
    def key(self) -> str:
        return f"{self.variant_id}:{self.gym_id or '-'}:{self.since.isoformat()}"

    @property
    def counted(self) -> list[Point]:
        return [point for point in self.points if point.counted]


def _reference(points: list[Point], point: Point) -> float | None:
    near = sorted(
        (other for other in points if other is not point and abs(other.day - point.day) <= REACH),
        key=lambda other: abs(other.day - point.day),
    )[:NEIGHBOURS]
    return median(other.e1rm for other in near) if len(near) >= 2 else None


def _outlier(point: Point, reference: float | None) -> Status:
    if not reference:
        return "counted"
    ratio = point.e1rm / reference
    if ratio > 1 + OUTLIER:
        return "high"
    if ratio < 1 / (1 + OUTLIER):
        return "low"
    return "counted"


def _isolated(points: list[Point], at: int) -> bool:
    value = points[at].e1rm
    sides = [points[max(0, at - 3) : at], points[at + 1 : at + 4]]
    levels = [median(p.e1rm for p in side) for side in sides if len(side) >= 2]
    return bool(levels) and all(
        not 1 / (1 + OUTLIER) <= value / level <= 1 + OUTLIER for level in levels
    )


def _steady(values: list[float]) -> bool:
    middle = median(values)
    return sum(abs(value / middle - 1) <= STEADY for value in values) >= len(values) - 1


def _step_at(points: list[Point], joined: set[date]) -> int | None:
    found: tuple[float, int] | None = None
    for at in range(STEP_SIDE, len(points) - STEP_SIDE + 1):
        if points[at].day in joined:
            continue
        before = [point.e1rm for point in points[at - STEP_SIDE : at]]
        after = [point.e1rm for point in points[at : at + STEP_SIDE]]
        if not (_steady(before) and _steady(after)):
            continue
        jump = math.log(median(after) / median(before))
        if abs(jump) <= math.log(1 + STEP):
            continue
        if jump < 0 and points[at].day - points[at - 1].day > LONG_BREAK:
            continue
        if found is None or abs(jump) > found[0]:
            found = (abs(jump), at)
    return found[1] if found else None


def _steps(points: list[Point], joined: set[date]) -> list[date]:
    at = _step_at(points, joined)
    if at is None:
        return []
    return [*_steps(points[:at], joined), points[at].day, *_steps(points[at:], joined)]


def series_of(points: Iterable[Point], marks: Iterable[Mark] = ()) -> list[Series]:
    by_machine: dict[tuple[str, str | None], list[Point]] = defaultdict(list)
    for point in points:
        by_machine[(point.variant_id, point.gym_id)].append(point)
    splits: dict[tuple[str, str | None], set[date]] = defaultdict(set)
    joins: dict[tuple[str, str | None], set[date]] = defaultdict(set)
    for mark in marks:
        (splits if mark.kind == "split" else joins)[(mark.variant_id, mark.gym_id)].add(mark.day)

    out: list[Series] = []
    for machine, found in by_machine.items():
        found.sort(key=lambda point: (point.day, point.id))
        pieces: list[tuple[list[Point], Start]] = []
        for point in found:
            previous = pieces[-1][0][-1] if pieces else None
            if previous is None:
                pieces.append(([point], "first"))
            elif any(previous.day < day <= point.day for day in splits[machine]):
                pieces.append(([point], "mark"))
            else:
                pieces[-1][0].append(point)
        for piece, start in pieces:
            clean = [p for at, p in enumerate(piece) if not _isolated(piece, at)]
            cuts = set(_steps(clean, joins[machine]))
            segment: list[Point] = []
            opened: Start = start
            for point in piece:
                if segment and point.day in cuts and segment[-1].day < point.day:
                    out.append(Series(machine[0], machine[1], segment, opened))
                    segment, opened = [], "detected"
                segment.append(point)
            out.append(Series(machine[0], machine[1], segment, opened))
    return out


def judge(series: Series, verdicts: dict[str, Verdict]) -> Series:
    judged = []
    for point in series.points:
        reference = _reference(series.points, point)
        status = _outlier(point, reference)
        verdict = verdicts.get(point.id)
        if verdict is not None:
            status = verdict
        judged.append(replace(point, status=status, reference=reference, verdict=verdict))
    return Series(series.variant_id, series.gym_id, judged, series.start)


def build(
    points: Iterable[Point],
    marks: Iterable[Mark] = (),
    verdicts: dict[str, Verdict] | None = None,
) -> list[Series]:
    return [judge(series, verdicts or {}) for series in series_of(points, marks)]


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


@dataclass
class Curve:
    start: date
    values: list[float] = field(default_factory=list)

    def at(self, day: date) -> float | None:
        if not self.values:
            return None
        index = (monday(day) - self.start).days // 7
        return self.values[max(0, min(index, len(self.values) - 1))]


def fit(series: Iterable[Series], until: date) -> Curve | None:
    used = [
        counted
        for serie in series
        if (counted := [p for p in serie.counted if p.day - serie.since >= CALIBRATION])
    ]
    if not used:
        return None
    start = monday(min(counted[0].day for counted in used))
    weeks = (monday(until) - start).days // 7 + 1
    if weeks < 1:
        return None
    rows = [
        (min((monday(point.day) - start).days // 7, weeks - 1), weeks + index, point)
        for index, counted in enumerate(used)
        for point in counted
    ]
    values = np.array([math.log(point.e1rm) for _, _, point in rows])
    base = np.array([point.index_weight / 3 for _, _, point in rows])
    weeks_of = np.array([week for week, _, _ in rows])
    levels_of = np.array([level for _, level, _ in rows])
    size = weeks + len(used)

    series_of = levels_of - weeks
    count = len(used)
    steps = np.arange(1, weeks)

    weights = base.copy()
    solution = np.zeros(size)
    for _ in range(4):
        week_diagonal = np.bincount(weeks_of, weights, minlength=weeks) + 1e-6
        level_diagonal = np.bincount(series_of, weights, minlength=count) + 1e-6
        cross = np.bincount(weeks_of * count + series_of, weights, minlength=weeks * count).reshape(
            weeks, count
        )
        week_target = np.bincount(weeks_of, weights * values, minlength=weeks)
        level_target = np.bincount(series_of, weights * values, minlength=count)

        matrix = np.diag(week_diagonal)
        matrix[steps, steps] += SMOOTHING
        matrix[steps - 1, steps - 1] += SMOOTHING
        matrix[steps, steps - 1] -= SMOOTHING
        matrix[steps - 1, steps] -= SMOOTHING
        scaled = cross / level_diagonal
        matrix -= scaled @ cross.T
        curve = np.linalg.solve(matrix, week_target - scaled @ level_target)
        levels = (level_target - cross.T @ curve) / level_diagonal

        solution = np.concatenate([curve, levels])
        residuals = np.abs(values - solution[weeks_of] - solution[levels_of])
        weights = base * np.minimum(1.0, ROBUST / np.maximum(residuals, 1e-12))
    return Curve(start=start, values=[float(value) for value in solution[:weeks]])
