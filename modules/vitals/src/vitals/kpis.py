from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import labs, steps, weight


class StepsKpi(BaseModel):
    today: int | None
    mean_7: int | None
    mean_7_past: int | None
    mean_30: int | None
    goal: int | None


class WeightKpi(BaseModel):
    average_7: float | None
    change_30: float | None
    change_90: float | None
    goal: weight.Goal
    against_goal: str | None


class Kpis(BaseModel):
    steps: StepsKpi
    weight: WeightKpi
    ldl: labs.Latest | None


async def walked(connection: AsyncConnection, goal: weight.Goal | None = None) -> StepsKpi:
    if goal is None:
        goal = await weight.goal(connection)
    now = steps.today()
    days, received = await steps.read(connection, now - timedelta(days=29), now)
    found = steps.summarise(days, goal.steps_per_day, received, now)
    yesterday = now - timedelta(days=1)
    return StepsKpi(
        today=found.today.steps if found.today else None,
        mean_7=found.mean_7,
        mean_7_past=steps.mean_of(days, yesterday - timedelta(days=6), yesterday),
        mean_30=found.mean_30,
        goal=goal.steps_per_day,
    )


async def read(connection: AsyncConnection) -> Kpis:
    goal = await weight.goal(connection)
    weighed = await weight.summary(connection, entries=0)
    return Kpis(
        steps=await walked(connection, goal),
        weight=WeightKpi(
            average_7=weighed.latest.avg7 if weighed.latest else None,
            change_30=weighed.change_30,
            change_90=weighed.change_90,
            goal=weighed.goal,
            against_goal=weighed.against_goal,
        ),
        ldl=await labs.latest(connection, "ldl"),
    )
