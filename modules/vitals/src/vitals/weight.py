from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import BODY_WEIGHT, body_weight
from vitals import steps

WINDOW_DAYS = 7
CHANGE_SLACK_DAYS = 7

Source = Literal["manual", "claude", "history"]


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


def today() -> date:
    return datetime.now(steps.zone()).date()


class WeightIn(BaseModel):
    kg: float = Field(ge=20, le=400)
    day: date | None = None
    at: time | None = None
    note: str | None = Field(default=None, max_length=200)


class Entry(BaseModel):
    id: str
    day: date
    at: time | None
    kg: float
    source: Source
    note: str | None


class Logged(BaseModel):
    entry: Entry
    already: bool


class Day(BaseModel):
    day: date
    kg: float
    avg7: float


class Goal(BaseModel):
    steps_per_day: int | None = Field(default=None, ge=100, le=100000)
    weight_min_kg: float | None = Field(default=None, ge=20, le=400)
    weight_max_kg: float | None = Field(default=None, ge=20, le=400)
    weight_direction: Literal["up", "down"] | None = None


class Summary(BaseModel):
    days: list[Day]
    entries: list[Entry]
    latest: Day | None
    change_30: float | None
    change_90: float | None
    goal: Goal
    against_goal: Literal["below", "inside", "above"] | None


def _num(value: Decimal | float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _entry(row) -> Entry:
    return Entry(
        id=str(row.id), day=row.day, at=row.at, kg=float(row.kg), source=row.source, note=row.note
    )


INSERT = text("""
    insert into vitals.vitals_weight (day, at, kg, source, note)
    values (:day, :at, :kg, :source, :note)
    on conflict (user_id, day, kg) do nothing
    returning id, day, at, kg, source, note
""")

SAME = text("""
    select id, day, at, kg, source, note from vitals.vitals_weight
    where day = :day and kg = :kg
""")

ENQUEUE = text("""
    insert into vitals.vitals_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :dedup)
    on conflict do nothing
""")


async def _publish(connection: AsyncConnection, entry: Entry) -> None:
    await connection.execute(
        ENQUEUE,
        {
            "type": "vitals.weight",
            "payload": json.dumps(
                {
                    "weight_id": entry.id,
                    "day": entry.day.isoformat(),
                    "kg": entry.kg,
                    BODY_WEIGHT: body_weight(id=entry.id, day=entry.day, kg=entry.kg),
                }
            ),
            "dedup": f"body_weight:{entry.id}:{entry.kg:.2f}",
        },
    )


EVERY_WEIGHING = text("select id, day, at, kg, source, note from vitals.vitals_weight")


async def backfill(connection: AsyncConnection) -> int:
    rows = (await connection.execute(EVERY_WEIGHING)).all()
    for row in rows:
        await _publish(connection, _entry(row))
    return len(rows)


async def log(connection: AsyncConnection, weighing: WeightIn, source: Source = "manual") -> Logged:
    values = {
        "day": weighing.day or today(),
        "at": weighing.at,
        "kg": round(Decimal(str(weighing.kg)), 2),
        "source": source,
        "note": (weighing.note or "").strip() or None,
    }
    row = (await connection.execute(INSERT, values)).one_or_none()
    if row is None:
        existing = (await connection.execute(SAME, values)).one()
        return Logged(entry=_entry(existing), already=True)
    entry = _entry(row)
    await _publish(connection, entry)
    return Logged(entry=entry, already=False)


UPDATE = text("""
    update vitals.vitals_weight
    set day = :day, at = :at, kg = :kg, note = :note
    where id = cast(:id as uuid)
    returning id, day, at, kg, source, note
""")


async def correct(connection: AsyncConnection, weight_id: str, weighing: WeightIn) -> Entry:
    values = {
        "id": weight_id,
        "day": weighing.day or today(),
        "at": weighing.at,
        "kg": round(Decimal(str(weighing.kg)), 2),
        "note": (weighing.note or "").strip() or None,
    }
    try:
        async with connection.begin_nested():
            row = (await connection.execute(UPDATE, values)).one_or_none()
    except IntegrityError as error:
        raise Conflict("that day already has a weigh-in with that weight") from error
    if row is None:
        raise NotFound(f"weigh-in {weight_id}")
    entry = _entry(row)
    await _publish(connection, entry)
    return entry


TYPED_THAT_DAY = text("""
    select id, day, at, kg, source, note from vitals.vitals_weight
    where day = :day and source = 'manual'
    order by created_at desc
    limit 1
""")


async def set_day(connection: AsyncConnection, kg: float, day: date | None = None) -> Logged:
    on = day or today()
    typed = (await connection.execute(TYPED_THAT_DAY, {"day": on})).one_or_none()
    if typed is None:
        return await log(connection, WeightIn(kg=kg, day=on))
    current = _entry(typed)
    if round(current.kg, 2) == round(kg, 2):
        return Logged(entry=current, already=True)
    try:
        entry = await correct(
            connection, current.id, WeightIn(kg=kg, day=on, at=current.at, note=current.note)
        )
    except Conflict:
        same = (await connection.execute(SAME, {"day": on, "kg": round(Decimal(str(kg)), 2)})).one()
        return Logged(entry=_entry(same), already=True)
    return Logged(entry=entry, already=False)


def daily(rows: list[tuple[date, float]]) -> list[Day]:
    by_day: dict[date, list[float]] = {}
    for day, kg in rows:
        by_day.setdefault(day, []).append(kg)
    days = sorted(by_day)
    means = [sum(by_day[day]) / len(by_day[day]) for day in days]
    out: list[Day] = []
    start = 0
    for index, day in enumerate(days):
        while days[start] <= day - timedelta(days=WINDOW_DAYS):
            start += 1
        window = means[start : index + 1]
        average = round(sum(window) / len(window), 2)
        out.append(Day(day=day, kg=round(means[index], 2), avg7=average))
    return out


def change(days: list[Day], back: int) -> float | None:
    if not days:
        return None
    last = days[-1]
    target = last.day - timedelta(days=back)
    before = [one for one in days if one.day <= target]
    if not before or target - before[-1].day > timedelta(days=CHANGE_SLACK_DAYS):
        return None
    return round(last.avg7 - before[-1].avg7, 2)


def reference(days: list[Day], back: int) -> Day | None:
    if not days:
        return None
    target = days[-1].day - timedelta(days=back)
    before = [one for one in days if one.day <= target]
    return before[-1] if before else None


def against(goal: Goal, value: float | None) -> Literal["below", "inside", "above"] | None:
    if value is None or (goal.weight_min_kg is None and goal.weight_max_kg is None):
        return None
    if goal.weight_min_kg is not None and value < goal.weight_min_kg:
        return "below"
    if goal.weight_max_kg is not None and value > goal.weight_max_kg:
        return "above"
    return "inside"


ALL = text("select day, kg from vitals.vitals_weight order by day, created_at")
RECENT = text("""
    select id, day, at, kg, source, note from vitals.vitals_weight
    order by day desc, at desc nulls last, created_at desc
    limit :limit
""")
GOAL = text(
    "select steps_per_day, weight_min_kg, weight_max_kg, weight_direction from vitals.vitals_goal"
)


async def goal(connection: AsyncConnection) -> Goal:
    row = (await connection.execute(GOAL)).one_or_none()
    if row is None:
        return Goal()
    return Goal(
        steps_per_day=row.steps_per_day,
        weight_min_kg=_num(row.weight_min_kg),
        weight_max_kg=_num(row.weight_max_kg),
        weight_direction=row.weight_direction,
    )


SET_GOAL = text("""
    insert into vitals.vitals_goal (steps_per_day, weight_min_kg, weight_max_kg, weight_direction)
    values (:steps_per_day, :weight_min_kg, :weight_max_kg, :weight_direction)
    on conflict (user_id) do update set
        steps_per_day = excluded.steps_per_day,
        weight_min_kg = excluded.weight_min_kg,
        weight_max_kg = excluded.weight_max_kg,
        weight_direction = excluded.weight_direction,
        updated_at = now()
""")


async def set_goal(connection: AsyncConnection, wanted: Goal) -> Goal:
    if (
        wanted.weight_min_kg is not None
        and wanted.weight_max_kg is not None
        and wanted.weight_min_kg > wanted.weight_max_kg
    ):
        raise Conflict("the weight band minimum cannot exceed the maximum")
    await connection.execute(SET_GOAL, wanted.model_dump())
    return await goal(connection)


async def summary(connection: AsyncConnection, entries: int = 30) -> Summary:
    rows = [(row.day, float(row.kg)) for row in (await connection.execute(ALL)).all()]
    days = daily(rows)
    recent = (await connection.execute(RECENT, {"limit": entries})).all()
    wanted = await goal(connection)
    latest = days[-1] if days else None
    return Summary(
        days=days,
        entries=[_entry(row) for row in recent],
        latest=latest,
        change_30=change(days, 30),
        change_90=change(days, 90),
        goal=wanted,
        against_goal=against(wanted, latest.avg7 if latest else None),
    )
