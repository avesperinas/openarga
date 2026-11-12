from __future__ import annotations

from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import body, heart, sleep, today, workouts
from vitals.steps import MADRID
from vitals.steps import today as current_day

RESERVE = 0.25
REST_DAYS = 30
SETTLE = 2
AFTER_WORKOUT = timedelta(minutes=10)


class Tension(BaseModel):
    day: date
    minutes: int
    still_minutes: int
    by_hour: list[int]
    threshold: float
    resting: float


class Morning(BaseModel):
    score: int | None
    hrv_z: float | None
    resting_z: float | None
    days_left: int


class Stress(BaseModel):
    tension: Tension | None
    morning: Morning
    missing: str | None = None


async def resting_reference(connection: AsyncConnection, day: date) -> float | None:
    since = day - timedelta(days=REST_DAYS)
    found = await body.read(connection, "resting_heart_rate", since=since, until=day)
    recent = [one.value for one in found.get("resting_heart_rate", [])]
    return sum(recent) / len(recent) if recent else None


def quiet_minutes(
    buckets: list[heart.Bucket], steps: dict[int, int], excluded: set[int]
) -> list[heart.Bucket]:
    out = []
    for one in buckets:
        if one.minute in excluded or steps.get(one.minute) != 0:
            continue
        before = [steps.get(one.minute - back) for back in range(1, SETTLE + 1)]
        if all(count == 0 for count in before):
            out.append(one)
    return out


def clock_minute(day: date, moment: datetime) -> int:
    local = moment.astimezone(MADRID)
    if local.date() != day:
        return -1 if local.date() < day else 1440
    return local.hour * 60 + local.minute


def excluded_minutes(day: date, spans: list[tuple[datetime, datetime]]) -> set[int]:
    out: set[int] = set()
    for start, end in spans:
        first = max(0, clock_minute(day, start))
        last = min(1439, clock_minute(day, end))
        out.update(range(first, last + 1))
    return out


async def tension(connection: AsyncConnection, day: date) -> tuple[Tension | None, str | None]:
    found = await heart.of_day(connection, day)
    if found is None or not found.buckets:
        return None, "todavía no ha llegado el vitals de hoy"
    steps = {one.minute: one.steps for one in found.buckets if one.steps is not None}
    if not steps:
        return None, "el vitals de este día llegó sin los pasos de cada minuto"
    resting = await resting_reference(connection, day)
    if resting is None:
        return None, "falta tu FC en reposo"
    top = await workouts.max_heart_rate(connection)
    threshold = resting + RESERVE * (top - resting)
    spans = [
        (start, end + AFTER_WORKOUT) for start, end in await workouts.spans(connection, day, day)
    ]
    for night in await sleep.read(connection, day, day + timedelta(days=1)):
        spans.append((night.start, night.end))
    quiet = quiet_minutes(found.buckets, steps, excluded_minutes(day, spans))
    high = [one for one in quiet if one.avg >= threshold]
    by_hour = [0] * 24
    for one in high:
        by_hour[one.minute // 60] += found.step
    return (
        Tension(
            day=day,
            minutes=len(high) * found.step,
            still_minutes=len(quiet) * found.step,
            by_hour=by_hour,
            threshold=round(threshold, 1),
            resting=round(resting, 1),
        ),
        None,
    )


def z(baseline: today.Baseline) -> float | None:
    if baseline.value is None or baseline.mean is None or baseline.high is None:
        return None
    spread = baseline.high - baseline.mean
    return None if spread <= 0 else (baseline.value - baseline.mean) / spread


async def morning(connection: AsyncConnection, day: date) -> Morning:
    found = {one.id: one for one in await today.baselines(connection, day)}
    hrv, resting = found["hrv_ms"], found["resting_heart_rate"]
    hrv_z, resting_z = z(hrv), z(resting)
    if hrv_z is None or resting_z is None:
        return Morning(
            score=None,
            hrv_z=hrv_z,
            resting_z=resting_z,
            days_left=max(0, today.ENOUGH - hrv.days),
        )
    score = max(0, min(100, round(50 + 12.5 * (hrv_z - resting_z))))
    return Morning(score=score, hrv_z=round(hrv_z, 2), resting_z=round(resting_z, 2), days_left=0)


async def read(connection: AsyncConnection, day: date | None = None) -> Stress:
    day = day or current_day()
    found, missing = await tension(connection, day)
    return Stress(tension=found, morning=await morning(connection, day), missing=missing)
