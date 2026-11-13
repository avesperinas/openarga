from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import memo, steps
from vitals.steps import Period, start_of, today

Group = Literal["heart", "activity", "breath", "gait", "more", "history"]
Kind = Literal["mean", "sum", "last"]


@dataclass(frozen=True)
class Metric:
    id: str
    group: Group
    name: str
    unit: str
    digits: int
    kind: Kind
    about: str


METRICS: tuple[Metric, ...] = (
    Metric(
        "resting_heart_rate",
        "heart",
        "Resting HR",
        "bpm",
        0,
        "mean",
        "The beats per minute at rest that the watch works out each day.",
    ),
    Metric(
        "sleep_heart_rate",
        "heart",
        "Sleeping HR",
        "bpm",
        0,
        "mean",
        "The average beats during non-REM sleep, measured by the band.",
    ),
    Metric(
        "heart_rate_avg",
        "heart",
        "Average HR",
        "bpm",
        0,
        "mean",
        "The average of every heart rate reading of the day.",
    ),
    Metric(
        "heart_rate_min",
        "heart",
        "Lowest HR",
        "bpm",
        0,
        "mean",
        "The lowest of the day.",
    ),
    Metric(
        "heart_rate_max",
        "heart",
        "Highest HR",
        "bpm",
        0,
        "mean",
        "The highest of the day.",
    ),
    Metric(
        "walking_heart_rate",
        "heart",
        "Walking HR",
        "bpm",
        0,
        "mean",
        "The average beats while walking.",
    ),
    Metric(
        "hrv_ms",
        "heart",
        "Variability (HRV)",
        "ms",
        0,
        "mean",
        "How much the time between beats varies. Until the device changed, the Apple Watch one "
        "during the day (SDNN); since then, the band one during sleep (RMSSD): they are different "
        "numbers.",
    ),
    Metric(
        "hrv_deep_ms",
        "heart",
        "HRV in deep sleep",
        "ms",
        0,
        "mean",
        "The variability between beats (RMSSD) only in deep sleep, measured by the band.",
    ),
    Metric(
        "vo2max",
        "heart",
        "VO₂ max",
        "ml/kg·min",
        1,
        "mean",
        "The cardiorespiratory fitness estimate made by the watch or the band. Each brand works it"
        " out its own way.",
    ),
    Metric(
        "high_heart_rate_events",
        "heart",
        "High HR alerts",
        "",
        0,
        "sum",
        "The times the watch warned of a high heart rate at rest.",
    ),
    Metric(
        "low_heart_rate_events",
        "heart",
        "Low HR alerts",
        "",
        0,
        "sum",
        "The times the watch warned of a low heart rate.",
    ),
    Metric(
        "active_kcal",
        "activity",
        "Active calories",
        "kcal",
        0,
        "sum",
        "The energy spent moving, not counting the energy at rest.",
    ),
    Metric(
        "basal_kcal",
        "activity",
        "Resting calories",
        "kcal",
        0,
        "sum",
        "The energy the body spends without moving.",
    ),
    Metric(
        "distance_km",
        "activity",
        "Distance on foot",
        "km",
        1,
        "sum",
        "What was walked and run.",
    ),
    Metric(
        "active_zone_min",
        "activity",
        "Zone minutes",
        "min",
        0,
        "sum",
        "The minutes with the heart rate in the fat burn zone, which count one, or in cardio or "
        "peak, which count two. Measured by the band.",
    ),
    Metric(
        "light_active_min",
        "activity",
        "Lightly active minutes",
        "min",
        0,
        "sum",
        "The minutes of light activity, like walking slowly, counted by the band.",
    ),
    Metric(
        "moderate_active_min",
        "activity",
        "Moderately active minutes",
        "min",
        0,
        "sum",
        "The minutes of moderate activity, like brisk walking.",
    ),
    Metric(
        "vigorous_active_min",
        "activity",
        "Vigorously active minutes",
        "min",
        0,
        "sum",
        "The minutes of vigorous activity, like running.",
    ),
    Metric(
        "sedentary_min",
        "activity",
        "Sitting time",
        "min",
        0,
        "sum",
        "The minutes of the day barely moving, awake, counted by the band.",
    ),
    Metric(
        "hr_zone_light_min",
        "activity",
        "Heart rate in light zone",
        "min",
        0,
        "sum",
        "The minutes of the day with the heart rate in the lowest of the band's four zones.",
    ),
    Metric(
        "hr_zone_moderate_min",
        "activity",
        "Heart rate in moderate zone",
        "min",
        0,
        "sum",
        "The minutes of the day with the heart rate in the second zone.",
    ),
    Metric(
        "hr_zone_vigorous_min",
        "activity",
        "Heart rate in vigorous zone",
        "min",
        0,
        "sum",
        "The minutes of the day with the heart rate in the third zone.",
    ),
    Metric(
        "hr_zone_peak_min",
        "activity",
        "Heart rate in peak zone",
        "min",
        0,
        "sum",
        "The minutes of the day with the heart rate in the highest zone.",
    ),
    Metric(
        "exercise_min",
        "activity",
        "Exercise minutes",
        "min",
        0,
        "sum",
        "The green ring: minutes at a brisk pace or more.",
    ),
    Metric(
        "stand_hours",
        "activity",
        "Stand hours",
        "h",
        0,
        "sum",
        "The blue ring: hours with at least one minute standing.",
    ),
    Metric(
        "stand_min",
        "activity",
        "Stand minutes",
        "min",
        0,
        "sum",
        "The total time standing.",
    ),
    Metric(
        "flights",
        "activity",
        "Flights climbed",
        "",
        0,
        "sum",
        "Climbs of about three metres.",
    ),
    Metric(
        "cycling_km",
        "activity",
        "Cycling distance",
        "km",
        1,
        "sum",
        "What was pedalled with the watch on.",
    ),
    Metric(
        "physical_effort",
        "activity",
        "Effort",
        "MET",
        1,
        "mean",
        "The average intensity of the day, in MET.",
    ),
    Metric(
        "move_goal_kcal",
        "activity",
        "Move goal",
        "kcal",
        0,
        "last",
        "The red ring goal that day.",
    ),
    Metric(
        "exercise_goal_min",
        "activity",
        "Exercise goal",
        "min",
        0,
        "last",
        "The green ring goal that day.",
    ),
    Metric(
        "stand_goal_hours",
        "activity",
        "Stand goal",
        "h",
        0,
        "last",
        "The blue ring goal that day.",
    ),
    Metric(
        "respiratory_rate",
        "breath",
        "Breathing",
        "br/min",
        1,
        "mean",
        "Breaths per minute while asleep.",
    ),
    Metric(
        "respiratory_rate_deep",
        "breath",
        "Breathing in deep sleep",
        "br/min",
        1,
        "mean",
        "Breaths per minute during deep sleep.",
    ),
    Metric(
        "respiratory_rate_light",
        "breath",
        "Breathing in light sleep",
        "br/min",
        1,
        "mean",
        "Breaths per minute during light sleep.",
    ),
    Metric(
        "respiratory_rate_rem",
        "breath",
        "Breathing in REM",
        "br/min",
        1,
        "mean",
        "Breaths per minute during REM sleep.",
    ),
    Metric(
        "spo2_pct",
        "breath",
        "Blood oxygen (SpO₂)",
        "%",
        1,
        "mean",
        "The average oxygen saturation during sleep, measured by the band.",
    ),
    Metric(
        "spo2_min_pct",
        "breath",
        "Lowest SpO₂",
        "%",
        1,
        "mean",
        "The low end of oxygen saturation during sleep.",
    ),
    Metric(
        "spo2_max_pct",
        "breath",
        "Highest SpO₂",
        "%",
        1,
        "mean",
        "The high end of oxygen saturation during sleep.",
    ),
    Metric(
        "skin_temp_delta_c",
        "breath",
        "Skin temperature",
        "°C",
        1,
        "mean",
        "How far the skin temperature at night is from your baseline of the last weeks.",
    ),
    Metric(
        "walking_speed_kmh",
        "gait",
        "Walking speed",
        "km/h",
        1,
        "mean",
        "The average walking speed on the flat, measured by the iPhone in the pocket.",
    ),
    Metric(
        "step_length_cm",
        "gait",
        "Step length",
        "cm",
        0,
        "mean",
        "The average length of each step.",
    ),
    Metric(
        "double_support_pct",
        "gait",
        "Double support",
        "%",
        1,
        "mean",
        "The time of each step with both feet on the ground.",
    ),
    Metric(
        "asymmetry_pct",
        "gait",
        "Walking asymmetry",
        "%",
        1,
        "mean",
        "How much the steps of one foot differ from the other.",
    ),
    Metric(
        "steadiness_pct",
        "gait",
        "Walking steadiness",
        "%",
        0,
        "last",
        "The steadiness score the iPhone works out each week.",
    ),
    Metric(
        "six_minute_walk_m",
        "gait",
        "6-minute walk test",
        "m",
        0,
        "last",
        "What the iPhone estimates would be walked in six minutes.",
    ),
    Metric(
        "stair_up_ms",
        "gait",
        "Stair speed up",
        "m/s",
        2,
        "mean",
        "The vertical speed going up stairs.",
    ),
    Metric(
        "stair_down_ms",
        "gait",
        "Stair speed down",
        "m/s",
        2,
        "mean",
        "The vertical speed going down them.",
    ),
    Metric(
        "mindful_min",
        "more",
        "Mindful minutes",
        "min",
        0,
        "sum",
        "The watch's Mindfulness sessions.",
    ),
    Metric(
        "headphone_db",
        "more",
        "Headphone audio",
        "dB",
        0,
        "mean",
        "The average level of the sound that came through the headphones.",
    ),
    Metric(
        "environment_db",
        "more",
        "Environmental sound",
        "dB",
        0,
        "mean",
        "The average level of the noise around, measured by the watch.",
    ),
    Metric(
        "headphone_noise_events",
        "more",
        "Headphone alerts",
        "",
        0,
        "sum",
        "The times the weekly headphone volume limit was exceeded.",
    ),
    Metric(
        "environment_noise_events",
        "more",
        "Noise alerts",
        "",
        0,
        "sum",
        "The times the watch warned of loud environmental noise.",
    ),
)

BY_ID = {one.id: one for one in METRICS}
GROUPS: tuple[tuple[Group, str], ...] = (
    ("heart", "Heart"),
    ("activity", "Activity"),
    ("breath", "Breathing and temperature"),
    ("gait", "Gait"),
    ("more", "More"),
    ("history", "Apple Health history"),
)
CHANGES = frozenset({"hrv_ms", "vo2max", "active_kcal", "basal_kcal"})

LATEST = text("""
    with ranked as (
        select (payload->>'date')::date as day, source, ingested_at, ts,
               coalesce(payload->'metrics', '{}') as metrics,
               row_number() over (
                   partition by (payload->>'date')::date, source
                   order by ingested_at desc, ts desc
               ) as n
        from vitals.events
        where type = 'health.daily' and ingested_at >= :arrived
          and (payload->>'date')::date between :since and :until
    ),
    marked as (
        select *, max(case when n = 1 then array(
            select key from unnest(cast(:keys as text[])) as key where not metrics ? key
        ) end) over (partition by day, source) as missing
        from ranked
    )
    select distinct on (day, source, metric.key)
        day, source, metric.key as metric, metric.value::float as value, ingested_at, ts
    from marked, jsonb_each_text(metrics) as metric
    where (n = 1 or metrics ?| missing) and metric.key = any(cast(:keys as text[]))
    order by day, source, metric.key, n
""")

SWITCH = text(f"""
    with {steps.STARTED}
    select max(since) from started having count(*) > 1
""")

PROFILE = text("""
    select payload, ingested_at from vitals.events
    where type = 'health.profile'
    order by ingested_at desc, ts desc
""")


class Point(BaseModel):
    day: date
    value: float
    total: float | None = None


class Figure(BaseModel):
    id: str
    group: Group
    name: str
    unit: str
    digits: int
    kind: Kind
    about: str
    latest: Point | None
    mean_30: float | None
    mean_365: float | None
    days: int
    changed_on: date | None = None
    historic: bool = False
    weeks: list[float | None] = []


WEEKS = 26


def weekly(points: list[Point], now: date, weeks: int = WEEKS) -> list[float | None]:
    first = now - timedelta(days=now.weekday()) - timedelta(weeks=weeks - 1)
    sums = [0.0] * weeks
    counts = [0] * weeks
    for one in points:
        if one.day < first or one.day > now:
            continue
        index = (one.day - first).days // 7
        sums[index] += one.value
        counts[index] += 1
    return [round(sums[i] / counts[i], 4) if counts[i] else None for i in range(weeks)]


class Section(BaseModel):
    id: Group
    name: str
    figures: list[Figure]


class Profile(BaseModel):
    blood_type: str | None = None
    sex: Literal["female", "male", "other"] | None = None
    birth_date: date | None = None
    age: int | None = None
    height_cm: float | None = None
    cardio_medications: str | None = None
    walking_stride_cm: float | None = None
    running_stride_cm: float | None = None
    irn_enrolled: bool | None = None


class Overview(BaseModel):
    profile: Profile | None
    sections: list[Section]


class Series(BaseModel):
    figure: Figure
    points: list[Point]


def age(born: date, now: date) -> int:
    return now.year - born.year - ((now.month, now.day) < (born.month, born.day))


async def profile(connection: AsyncConnection) -> Profile | None:
    merged: dict = {}
    for row in (await connection.execute(PROFILE)).all():
        for key, value in row.payload.items():
            merged.setdefault(key, value)
    if not merged:
        return None
    found = Profile.model_validate(merged)
    if found.birth_date:
        found.age = age(found.birth_date, today())
    return found


async def switched_on(connection: AsyncConnection) -> date | None:
    return await connection.scalar(SWITCH)


async def read(
    connection: AsyncConnection,
    only: str | None = None,
    since: date = date.min,
    until: date = date.max,
    started: steps.Started | None = None,
) -> dict[str, list[Point]]:
    if only is not None and only not in BY_ID:
        return {}
    found = await kept(connection, since)
    if started is None and found.two_sources(since, until):
        started = await steps.started(connection)
    return found.points(since, until, started or {}, only)


async def raw(connection: AsyncConnection, since: date, until: date) -> list[Any]:
    bounds = {"arrived": steps.arrived(since), "since": since, "until": until}
    return (await connection.execute(LATEST, {**bounds, "keys": list(BY_ID)})).all()


ARRIVED = text("""
    select (payload->>'date')::date as day, max(ingested_at) as last
    from vitals.events
    where type = 'health.daily' and ingested_at > :after
    group by 1
""")


@dataclass
class Kept(memo.Read):
    first: date
    days: dict[date, list[Any]] = field(default_factory=dict)
    last: datetime | None = None
    chosen: dict[date, dict[str, Point]] = field(default_factory=dict)
    chosen_with: steps.Started | None = None
    mixed: set[date] = field(default_factory=set)

    def store(self, day: date, rows: list[Any]) -> None:
        self.days[day] = rows
        self.chosen.pop(day, None)
        if len({row.source for row in rows}) > 1:
            self.mixed.add(day)
        else:
            self.mixed.discard(day)

    def two_sources(self, since: date, until: date) -> bool:
        return any(since <= day <= until for day in self.mixed)

    def points(
        self, since: date, until: date, started: steps.Started, only: str | None = None
    ) -> dict[str, list[Point]]:
        if self.chosen_with != started:
            for day in self.mixed:
                self.chosen.pop(day, None)
            self.chosen_with = dict(started)
        out: dict[str, list[Point]] = {}
        for day in sorted(one for one in self.days if since <= one <= until):
            picked = self.chosen.get(day)
            if picked is None:
                picked = self.chosen[day] = pick(self.days[day], started)
            for metric, point in picked.items():
                if only is None or metric == only:
                    out.setdefault(metric, []).append(point)
        return out


def pick(rows: list[Any], started: steps.Started) -> dict[str, Point]:
    chosen = steps.choose(rows, key=lambda row: row.metric, known=started)
    return {row.metric: Point(day=row.day, value=row.value) for row in chosen}


async def kept(connection: AsyncConnection, since: date) -> Kept:
    found: Kept | None = memo.get("daily")
    if found is None or since < found.first or found.expired():
        found = Kept(first=since, last=await memo.last_arrival(connection, ("health.daily",)))
        by_day: dict[date, list[Any]] = {}
        for row in await raw(connection, since, date.max):
            by_day.setdefault(row.day, []).append(row)
        for day, rows in by_day.items():
            found.store(day, rows)
    else:
        touched = (await connection.execute(ARRIVED, {"after": memo.after(found.last)})).all()
        days = sorted(row.day for row in touched if row.day >= found.first)
        if days:
            fresh: dict[date, list[Any]] = {day: [] for day in days}
            for row in await raw(connection, days[0], days[-1]):
                if row.day in fresh:
                    fresh[row.day].append(row)
            for day, rows in fresh.items():
                found.store(day, rows)
        found.last = memo.latest(found.last, *(row.last for row in touched))
    memo.put("daily", None, found)
    return found


def mean(points: list[Point], since: date) -> float | None:
    values = [one.value for one in points if one.day >= since]
    return sum(values) / len(values) if values else None


def figure(metric: Metric, points: list[Point], now: date, switch: date | None = None) -> Figure:
    latest = points[-1] if points else None
    changes = switch is not None and metric.id in CHANGES
    side = points
    if changes and latest is not None:
        after = latest.day >= switch
        side = [one for one in points if (one.day >= switch) == after]
    return Figure(
        id=metric.id,
        group=metric.group,
        name=metric.name,
        unit=metric.unit,
        digits=metric.digits,
        kind=metric.kind,
        about=metric.about,
        latest=latest,
        mean_30=mean(side, now - timedelta(days=29)),
        mean_365=mean(side, now - timedelta(days=364)),
        days=len(points),
        changed_on=switch if changes else None,
        historic=(historic := switch is not None and latest is not None and latest.day < switch),
        weeks=[] if historic else weekly(points, now),
    )


async def overview(connection: AsyncConnection) -> Overview:
    started = await steps.started(connection)
    series = await read(connection, started=started)
    switch = steps.switch(started)
    now = today()
    figures = [
        figure(metric, series[metric.id], now, switch)
        for metric in METRICS
        if series.get(metric.id)
    ]
    return Overview(
        profile=await profile(connection),
        sections=[
            Section(
                id=group,
                name=name,
                figures=[
                    one
                    for one in figures
                    if (one.historic and group == "history")
                    or (not one.historic and one.group == group)
                ],
            )
            for group, name in GROUPS
        ],
    )


def grouped(
    points: list[Point], kind: Kind, period: Period, switch: date | None = None
) -> list[Point]:
    if period == "day":
        return points
    buckets: dict[date, list[float]] = {}
    for one in points:
        start = start_of(one.day, period)
        if switch is not None and one.day >= switch > start:
            start = switch
        buckets.setdefault(start, []).append(one.value)
    out = []
    for start, values in sorted(buckets.items()):
        if kind == "last":
            out.append(Point(day=start, value=values[-1]))
            continue
        total = round(sum(values), 2) if kind == "sum" else None
        out.append(Point(day=start, value=round(sum(values) / len(values), 2), total=total))
    return out


async def series(
    connection: AsyncConnection,
    metric_id: str,
    since: date | None = None,
    until: date | None = None,
    period: Period = "day",
) -> Series:
    metric = BY_ID[metric_id]
    started = await steps.started(connection)
    points = (await read(connection, metric_id, started=started)).get(metric_id, [])
    switch = steps.switch(started)
    kept = [
        one
        for one in points
        if (since is None or one.day >= since) and (until is None or one.day <= until)
    ]
    found = figure(metric, points, today(), switch)
    return Series(figure=found, points=grouped(kept, metric.kind, period, found.changed_on))
