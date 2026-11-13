from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import body, heart, kpis, memo, rhythm, sleep, steps, workouts
from vitals.steps import today, zone

WINDOW = 60
ENOUGH = 14

Status = Literal["below", "inside", "above"]

BASELINES: tuple[tuple[str, str, str, int], ...] = (
    ("sleep_min", "Sleep", "min", 0),
    ("hrv_ms", "HRV", "ms", 0),
    ("resting_heart_rate", "Resting HR", "bpm", 0),
    ("respiratory_rate", "Breathing", "br/min", 1),
    ("spo2_pct", "SpO₂", "%", 1),
    ("skin_temp_delta_c", "Skin temperature", "°C", 1),
)


class Baseline(BaseModel):
    id: str
    name: str
    unit: str
    digits: int
    day: date | None
    value: float | None
    mean: float | None
    low: float | None
    high: float | None
    status: Status | None
    days: int


class Pulse(BaseModel):
    minute: int
    bpm: float


class Today(BaseModel):
    day: date
    steps: kpis.StepsKpi
    pulse: Pulse | None
    baselines: list[Baseline]
    load: workouts.Load
    workouts: list[workouts.Workout]
    battery: rhythm.Device | None


class DayLine(BaseModel):
    day: date
    night: sleep.NightDetail | None
    heart: heart.Day | None
    workouts: list[workouts.Workout]


def band(points: list[tuple[date, float]], now: date, since: date | None = None):
    first = now - timedelta(days=WINDOW)
    if since is not None:
        first = max(first, since)
    values = [value for day, value in points if first <= day < now]
    if len(values) < ENOUGH:
        return None, None, None, len(values)
    mean = statistics.fmean(values)
    spread = statistics.pstdev(values)
    return mean, mean - spread, mean + spread, len(values)


def baseline(
    key: str,
    name: str,
    unit: str,
    digits: int,
    points: list[tuple[date, float]],
    now: date,
    switch: date | None,
) -> Baseline:
    recent = [one for one in points if now - timedelta(days=1) <= one[0] <= now]
    latest = recent[-1] if recent else None
    since = switch if key in body.CHANGES and switch is not None else None
    reference = latest[0] if latest else now
    mean, low, high, days = band(points, reference, since)
    status = None
    if latest is not None and mean is not None:
        value = latest[1]
        status = "below" if value < low else "above" if value > high else "inside"

    def rounded(value: float | None) -> float | None:
        return None if value is None else round(value, digits)

    return Baseline(
        id=key,
        name=name,
        unit=unit,
        digits=digits,
        day=latest[0] if latest else None,
        value=rounded(latest[1]) if latest else None,
        mean=rounded(mean),
        low=rounded(low),
        high=rounded(high),
        status=status,
        days=days,
    )


NORMALS_KEPT = 4


@dataclass
class Nights(memo.Read):
    first: date
    found: dict[str, Any] = field(default_factory=dict)
    last: datetime | None = None


async def _nights(connection: AsyncConnection, now: date) -> Nights:
    kept: Nights | None = memo.get("nights", now)
    if kept is None or kept.expired():
        kept = Nights(
            first=now - timedelta(days=WINDOW + 1),
            last=await memo.last_arrival(connection, ("health.sleep",)),
        )
        for row in await sleep.raw(connection, kept.first, now):
            kept.found[row.payload["id"]] = row
    else:
        arrived = await sleep.arrived_since(connection, memo.after(kept.last))
        for row in arrived:
            before = kept.found.get(row.payload["id"])
            if before is None or (row.ingested_at, row.ts) >= (before.ingested_at, before.ts):
                kept.found[row.payload["id"]] = row
        kept.last = memo.latest(kept.last, *(row.ingested_at for row in arrived))
    memo.put("nights", now, kept, keep=NORMALS_KEPT)
    return kept


async def baselines(connection: AsyncConnection, now: date | None = None) -> list[Baseline]:
    now = now or today()
    first = now - timedelta(days=WINDOW + 1)
    started = await steps.started(connection)
    daily = await body.read(connection, since=first, until=now, started=started)
    switch = steps.switch(started)
    kept = await _nights(connection, now)
    nights = sleep.nights_of([row.payload for row in kept.found.values()], first, now)
    out = []
    for key, name, unit, digits in BASELINES:
        if key == "sleep_min":
            points = [(one.day, float(one.minutes_asleep)) for one in nights]
        else:
            points = [(one.day, one.value) for one in daily.get(key, [])]
        out.append(baseline(key, name, unit, digits, points, now, switch))
    return out


async def read(connection: AsyncConnection, now: date | None = None) -> Today:
    now = now or today()
    devices = await rhythm.devices(connection)
    found = await heart.of_day(connection, now)
    last = found.buckets[-1] if found and found.buckets else None
    done = await workouts.between(connection, workouts.monday(now) - timedelta(weeks=11), now)
    return Today(
        day=now,
        steps=await kpis.walked(connection),
        pulse=Pulse(minute=last.minute, bpm=last.avg) if last else None,
        baselines=await baselines(connection, now),
        load=await workouts.load(connection, now=now, done=done),
        workouts=[
            one for one in done if one.start.astimezone(zone()).date() > now - timedelta(days=7)
        ],
        battery=devices[0] if devices else None,
    )


async def day_line(connection: AsyncConnection, day: date) -> DayLine:
    return DayLine(
        day=day,
        night=await sleep.night(connection, day),
        heart=await heart.of_day(connection, day),
        workouts=await workouts.between(connection, day, day),
    )
