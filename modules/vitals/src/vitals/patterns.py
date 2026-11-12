from __future__ import annotations

import statistics
from datetime import date, timedelta

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import body, sleep, workouts
from vitals.steps import MADRID, today

LATE_HOUR = 20
NIGHTS = 90


class Group(BaseModel):
    nights: int
    asleep: int | None
    deep: int | None
    hrv: float | None


class Comparison(BaseModel):
    label: str
    after: Group
    rest: Group


class Patterns(BaseModel):
    nights: int
    fell_asleep_spread: int | None
    woke_spread: int | None
    comparisons: list[Comparison]


def group(nights: list[sleep.Night], hrv: dict[date, float]) -> Group:
    deep = [one.stages["deep"] for one in nights if one.stages and "deep" in one.stages]
    found = [hrv[one.day] for one in nights if one.day in hrv]
    return Group(
        nights=len(nights),
        asleep=round(statistics.fmean(one.minutes_asleep for one in nights)) if nights else None,
        deep=round(statistics.fmean(deep)) if deep else None,
        hrv=round(statistics.fmean(found), 1) if found else None,
    )


def spread(values: list[int]) -> int | None:
    return round(statistics.pstdev(values)) if len(values) >= 7 else None


async def read(connection: AsyncConnection, now: date | None = None) -> Patterns:
    now = now or today()
    first = now - timedelta(days=NIGHTS - 1)
    every = await sleep.read(connection, first)
    last_30 = [one for one in every if one.day > now - timedelta(days=30)]
    done = await workouts.spans(connection, now - timedelta(days=NIGHTS + 1), now)
    trained: set[date] = set()
    late: set[date] = set()
    for start, end in done:
        day = start.astimezone(MADRID).date()
        trained.add(day)
        if end.astimezone(MADRID).hour >= LATE_HOUR:
            late.add(day)
    found = await body.read(connection, "hrv_ms", since=first)
    hrv = {one.day: one.value for one in found.get("hrv_ms", [])}

    def after(days: set[date]) -> tuple[list[sleep.Night], list[sleep.Night]]:
        yes = [one for one in every if one.day - timedelta(days=1) in days]
        return yes, [one for one in every if one not in yes]

    with_training, without_training = after(trained)
    after_late, not_late = after(late)
    return Patterns(
        nights=len(last_30),
        fell_asleep_spread=spread([sleep.clock(one.start) for one in last_30]),
        woke_spread=spread([sleep.clock(one.end) for one in last_30]),
        comparisons=[
            Comparison(
                label="Después de un día con entreno",
                after=group(with_training, hrv),
                rest=group(without_training, hrv),
            ),
            Comparison(
                label="Después de entrenar a partir de las 20:00",
                after=group(after_late, hrv),
                rest=group(not_late, hrv),
            ),
        ],
    )
