from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from macros import catalog
from macros.common import Conflict, now, timezone, zone

Meal = Literal["breakfast", "morning", "lunch", "snack", "dinner", "night"]


@dataclass(frozen=True)
class Slot:
    key: Meal
    start: time
    usual: time


SLOTS: tuple[Slot, ...] = (
    Slot("night", time(0, 0), time(1, 0)),
    Slot("breakfast", time(4, 0), time(8, 30)),
    Slot("morning", time(10, 30), time(11, 0)),
    Slot("lunch", time(13, 0), time(14, 30)),
    Slot("snack", time(17, 0), time(18, 0)),
    Slot("dinner", time(20, 0), time(21, 30)),
)
BY_KEY = {slot.key: slot for slot in SLOTS}
ORDER: tuple[Meal, ...] = tuple(slot.key for slot in SLOTS)
HISTORY_DAYS = 30


def meal_of(moment: datetime | time, tz: str | None = None) -> Meal:
    zone_ = ZoneInfo(tz or timezone())
    local = moment if isinstance(moment, time) else moment.astimezone(zone_).time()
    found: Meal = "night"
    for slot in SLOTS:
        if local >= slot.start:
            found = slot.key
    return found


def label(meal: Meal) -> str:
    return catalog.t(f"meal.{meal}")


def started(meal: Meal, day: date, moment: datetime | None = None) -> bool:
    current = (moment or now()).astimezone(zone())
    if day < current.date():
        return True
    if day > current.date():
        return False
    return current.time() >= BY_KEY[meal].start


USUAL = text("""
    select eaten_at, tz from macros.macros_entry
    where day between :first and :last and status = 'confirmed'
""")


async def usual_times(connection: AsyncConnection, day: date) -> dict[Meal, time]:
    rows = (
        await connection.execute(
            USUAL, {"first": day - timedelta(days=HISTORY_DAYS), "last": day - timedelta(days=1)}
        )
    ).all()
    minutes: dict[Meal, list[int]] = {}
    for row in rows:
        local = row.eaten_at.astimezone(ZoneInfo(row.tz or timezone()))
        minutes.setdefault(meal_of(local.time()), []).append(local.hour * 60 + local.minute)
    found: dict[Meal, time] = {}
    for slot in SLOTS:
        seen = minutes.get(slot.key)
        if seen:
            middle = int(statistics.median_low(seen))
            found[slot.key] = time(middle // 60, middle % 60)
        else:
            found[slot.key] = slot.usual
    return found


async def moment_for(
    connection: AsyncConnection, meal: Meal, day: date | None = None, at: datetime | None = None
) -> datetime:
    current = now()
    if at is not None:
        local = at if at.tzinfo else at.replace(tzinfo=zone())
        if meal_of(local) == meal:
            return local
        day = local.astimezone(zone()).date()
    on = day or current.date()
    if on == current.date() and meal_of(current) == meal:
        return current.replace(second=0, microsecond=0)
    usual = (await usual_times(connection, on))[meal]
    return datetime.combine(on, usual, zone())


class MealOut(BaseModel):
    meal: Meal
    label: str
    usual_at: str
    started: bool
    current: bool
    kcal: float
    protein: float
    entry_ids: list[str]
    planned_ids: list[str]


def check(meal: str) -> Meal:
    if meal not in BY_KEY:
        raise Conflict(f"'{meal}' is not a meal: {', '.join(ORDER)}")
    return meal  # type: ignore[return-value]
