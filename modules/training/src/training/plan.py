from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from training import bodyweight as weights

DayKind = Literal["push", "pull", "leg", "full", "other"]


class Option(BaseModel):
    variant_id: str
    name: str
    implement: str
    min_increment: float
    priority: int


class Slot(BaseModel):
    id: str
    position: int
    exercise: str
    target_sets: int
    rep_min: int
    rep_max: int
    allow_both: bool
    options: list[Option]


class Day(BaseModel):
    id: str
    name: str
    kind: DayKind
    position: int
    slots: list[Slot]


class ActivePlan(BaseModel):
    plan_id: str
    name: str
    version_id: str
    version: int
    valid_from: date
    days: list[Day]


CURRENT_VERSION = text("""
    select p.id as plan_id, p.name, v.id as version_id, v.number, v.valid_from
    from training.training_plan p
    join training.training_plan_version v on v.plan_id = p.id
    where p.active and v.published_at is not null
    order by v.number desc
    limit 1
""")

STRUCTURE = text("""
    select d.id as day_id, d.name as day_name, d.kind, d.position as day_position,
           s.id as slot_id, s.position as slot_position, s.target_sets, s.rep_min, s.rep_max,
           s.allow_both,
           o.variant_id, o.priority, va.name as variant_name, va.implement, va.min_increment,
           e.name as exercise
    from training.training_plan_day d
    left join training.training_plan_slot s on s.plan_day_id = d.id
    left join training.training_plan_slot_option o on o.plan_slot_id = s.id
    left join training.training_variant va on va.id = o.variant_id
    left join training.training_exercise e on e.id = va.exercise_id
    where d.plan_version_id = :version_id
    order by d.position, s.position, o.priority
""")


async def day_slots(connection: AsyncConnection, version_id: str, day_id: str) -> list[Slot]:
    days = await version_days(connection, version_id)
    return next((day.slots for day in days if day.id == day_id), [])


async def version_days(connection: AsyncConnection, version_id: str) -> list[Day]:
    days: dict[str, Day] = {}
    slots: dict[str, Slot] = {}
    for row in (await connection.execute(STRUCTURE, {"version_id": version_id})).all():
        day = days.setdefault(
            str(row.day_id),
            Day(
                id=str(row.day_id),
                name=row.day_name,
                kind=row.kind,
                position=row.day_position,
                slots=[],
            ),
        )
        if row.slot_id is None:
            continue
        slot = slots.get(str(row.slot_id))
        if slot is None:
            slot = Slot(
                id=str(row.slot_id),
                position=row.slot_position,
                exercise=row.exercise or "",
                target_sets=row.target_sets,
                rep_min=row.rep_min,
                rep_max=row.rep_max,
                allow_both=row.allow_both,
                options=[],
            )
            slots[str(row.slot_id)] = slot
            day.slots.append(slot)
        if row.variant_id is not None:
            slot.options.append(
                Option(
                    variant_id=str(row.variant_id),
                    name=row.variant_name,
                    implement=row.implement,
                    min_increment=float(row.min_increment),
                    priority=row.priority,
                )
            )
    return list(days.values())


async def active_plan(connection: AsyncConnection) -> ActivePlan | None:
    current = (await connection.execute(CURRENT_VERSION)).one_or_none()
    if current is None:
        return None

    return ActivePlan(
        plan_id=str(current.plan_id),
        name=current.name,
        version_id=str(current.version_id),
        version=current.number,
        valid_from=current.valid_from,
        days=await version_days(connection, str(current.version_id)),
    )


class Settings(BaseModel):
    weekly_goal: int
    unit: str
    default_increments: dict[str, float]
    bodyweight: float | None = None


DEFAULT_SETTINGS = Settings(
    weekly_goal=5,
    unit="kg",
    default_increments={
        "barbell": 2.5,
        "dumbbell": 2,
        "smith": 2.5,
        "machine": 5,
        "cable": 5,
        "bodyweight": 1,
    },
)


async def settings(connection: AsyncConnection) -> Settings:
    row = (
        await connection.execute(
            text("select weekly_goal, unit, default_increments from training.training_settings")
        )
    ).one_or_none()
    kg = await connection.scalar(weights.LATEST)
    bodyweight = float(kg) if kg is not None else None
    if row is None:
        return DEFAULT_SETTINGS.model_copy(update={"bodyweight": bodyweight})
    return Settings(
        weekly_goal=row.weekly_goal,
        unit=row.unit,
        default_increments=row.default_increments,
        bodyweight=bodyweight,
    )
