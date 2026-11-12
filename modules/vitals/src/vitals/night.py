from __future__ import annotations

from datetime import date, datetime, time, timedelta

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import heart, sleep, today
from vitals.steps import MADRID

NIGHT_FIGURES = ("hrv_ms", "respiratory_rate", "spo2_pct", "skin_temp_delta_c")


class Pulse(BaseModel):
    at: datetime
    bpm: float


class Page(BaseModel):
    night: sleep.NightDetail
    heart: list[Pulse]
    figures: list[today.Baseline]
    mean_30: sleep.Means
    previous: date | None
    next: date | None


async def pulse_between(connection: AsyncConnection, start: datetime, end: datetime) -> list[Pulse]:
    out: list[Pulse] = []
    day = start.astimezone(MADRID).date()
    while day <= end.astimezone(MADRID).date():
        found = await heart.of_day(connection, day)
        midnight = datetime.combine(day, time(0), MADRID)
        for one in found.buckets if found else []:
            at = midnight + timedelta(minutes=one.minute)
            if start <= at <= end:
                out.append(Pulse(at=at, bpm=one.avg))
        day += timedelta(days=1)
    return out


async def page(connection: AsyncConnection, day: date) -> Page | None:
    first = day - timedelta(days=30)
    nights = await sleep.read(connection, first)
    found = next((index for index, one in enumerate(nights) if one.day == day), None)
    if found is None:
        return None
    night = nights[found]
    before = [one for one in nights if first <= one.day < day]
    previous = nights[found - 1].day if found > 0 else None
    if previous is None:
        older = await sleep.read(connection, until=first - timedelta(days=1))
        previous = older[-1].day if older else None
    figures = [one for one in await today.baselines(connection, day) if one.id in NIGHT_FIGURES]
    return Page(
        night=night,
        heart=await pulse_between(connection, night.start, night.end),
        figures=[one for one in figures if one.day == day],
        mean_30=sleep.means(before),
        previous=previous,
        next=nights[found + 1].day if found + 1 < len(nights) else None,
    )
