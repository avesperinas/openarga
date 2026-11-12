from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from training import links, plan
from training.training import Conflict, NotFound, local_day

Name = Annotated[str, Field(min_length=1, max_length=80, pattern=r"\S")]
Pattern = Literal[
    "horizontal_push",
    "vertical_push",
    "horizontal_pull",
    "vertical_pull",
    "knee_dominant",
    "hip_dominant",
    "isolation",
]
Implement = Literal["barbell", "dumbbell", "smith", "machine", "cable", "bodyweight"]


class Variant(BaseModel):
    id: str
    exercise_id: str
    name: str
    implement: str
    gym_id: str | None
    min_increment: float
    index_weight: int


class Exercise(BaseModel):
    id: str
    name: str
    pattern: str
    load_type: str
    muscles: dict[str, float]
    variants: list[Variant]


class Gym(BaseModel):
    id: str
    name: str
    active: bool


class Muscle(BaseModel):
    id: str
    name: str
    region: str


class Catalogue(BaseModel):
    exercises: list[Exercise]
    gyms: list[Gym]
    muscles: list[Muscle]


async def catalogue(connection: AsyncConnection) -> Catalogue:
    exercises = {
        str(row.id): Exercise(
            id=str(row.id),
            name=row.name,
            pattern=row.pattern,
            load_type=row.load_type,
            muscles={},
            variants=[],
        )
        for row in await connection.execute(
            text(
                "select id, name, pattern, load_type from training.training_exercise order by name"
            )
        )
    }
    for row in await connection.execute(
        text("select exercise_id, muscle_id, contribution from training.training_exercise_muscle")
    ):
        exercises[str(row.exercise_id)].muscles[row.muscle_id] = float(row.contribution)
    for row in await connection.execute(
        text(
            "select id, exercise_id, name, implement, gym_id, min_increment, index_weight "
            "from training.training_variant where active order by name"
        )
    ):
        exercises[str(row.exercise_id)].variants.append(
            Variant(
                id=str(row.id),
                exercise_id=str(row.exercise_id),
                name=row.name,
                implement=row.implement,
                gym_id=str(row.gym_id) if row.gym_id else None,
                min_increment=float(row.min_increment),
                index_weight=row.index_weight,
            )
        )
    gyms = [
        Gym(id=str(row.id), name=row.name, active=row.active)
        for row in await connection.execute(
            text("select id, name, active from training.training_gym order by name")
        )
    ]
    muscles = [
        Muscle(id=row.id, name=row.name, region=row.region)
        for row in await connection.execute(
            text("select id, name, region from training.training_muscle order by region, name")
        )
    ]
    return Catalogue(exercises=list(exercises.values()), gyms=gyms, muscles=muscles)


class VariantIn(BaseModel):
    name: Name
    implement: Implement
    gym_id: str | None = None
    min_increment: Annotated[float, Field(gt=0, le=100)] | None = None
    index_weight: Literal[1, 2, 3] | None = None


Muscles = dict[str, Literal[0.5, 1.0]]


def _one_primary(muscles: Muscles) -> Muscles:
    if sum(1 for contribution in muscles.values() if contribution == 1.0) > 1:
        raise ValueError(
            "un ejercicio tiene un solo músculo principal: el que mide su fuerza. "
            "Los demás van como secundarios"
        )
    return muscles


class ExerciseIn(BaseModel):
    name: Name
    pattern: Pattern
    muscles: Annotated[Muscles, AfterValidator(_one_primary)] = {}
    variant: VariantIn


def _default_weight(pattern: str) -> int:
    return 1 if pattern == "isolation" else 2


async def _increment(connection: AsyncConnection, implement: str) -> float:
    increments = (await plan.settings(connection)).default_increments
    return float(increments.get(implement, 1))


async def create_exercise(connection: AsyncConnection, request: ExerciseIn) -> Exercise:
    taken = await connection.scalar(
        text("select 1 from training.training_exercise where lower(name) = lower(:name)"),
        {"name": request.name.strip()},
    )
    if taken:
        raise Conflict(f"ya existe un ejercicio que se llama «{request.name.strip()}»")
    bodyweight = request.variant.implement == "bodyweight"
    exercise_id = await connection.scalar(
        text(
            "insert into training.training_exercise (name, pattern, load_type, bodyweight_factor) "
            "values (:name, :pattern, :load, :factor) returning id"
        ),
        {
            "name": request.name.strip(),
            "pattern": request.pattern,
            "load": "weighted_bodyweight" if bodyweight else "external",
            "factor": 1.0 if bodyweight else None,
        },
    )
    await _write_muscles(connection, str(exercise_id), request.muscles)
    await create_variant(connection, str(exercise_id), request.variant)
    found = next(e for e in (await catalogue(connection)).exercises if e.id == str(exercise_id))
    return found


async def _write_muscles(connection: AsyncConnection, exercise_id: str, muscles: Muscles) -> None:
    known = set(
        (await connection.execute(text("select id from training.training_muscle"))).scalars()
    )
    unknown = sorted(set(muscles) - known)
    if unknown:
        raise Conflict(f"músculos que no existen: {', '.join(unknown)}")
    await connection.execute(
        text("delete from training.training_exercise_muscle where exercise_id = :e"),
        {"e": exercise_id},
    )
    for muscle, contribution in muscles.items():
        await connection.execute(
            text(
                "insert into training.training_exercise_muscle (exercise_id, muscle_id, contribution) "
                "values (:e, :m, :c)"
            ),
            {"e": exercise_id, "m": muscle, "c": contribution},
        )


class MusclesIn(BaseModel):
    muscles: Annotated[Muscles, AfterValidator(_one_primary)]


async def update_muscles(
    connection: AsyncConnection, exercise_id: str, request: MusclesIn
) -> Exercise:
    exists = await connection.scalar(
        text("select 1 from training.training_exercise where id = :id"), {"id": exercise_id}
    )
    if not exists:
        raise NotFound(exercise_id)
    await _write_muscles(connection, exercise_id, request.muscles)
    return next(e for e in (await catalogue(connection)).exercises if e.id == exercise_id)


async def create_variant(
    connection: AsyncConnection, exercise_id: str, request: VariantIn
) -> Variant:
    pattern = await connection.scalar(
        text("select pattern from training.training_exercise where id = :id"), {"id": exercise_id}
    )
    if pattern is None:
        raise NotFound(exercise_id)
    taken = await connection.scalar(
        text(
            "select 1 from training.training_variant where exercise_id = :e and implement = :i "
            "and gym_id is not distinct from cast(:g as uuid)"
        ),
        {"e": exercise_id, "i": request.implement, "g": request.gym_id},
    )
    if taken:
        raise Conflict("ese ejercicio ya tiene una variante con ese implemento en ese centro")
    increment = request.min_increment or await _increment(connection, request.implement)
    weight = request.index_weight or _default_weight(pattern)
    row = (
        await connection.execute(
            text(
                "insert into training.training_variant "
                "(exercise_id, name, implement, gym_id, min_increment, index_weight) "
                "values (:e, :name, :implement, cast(:gym as uuid), :increment, :weight) "
                "returning id"
            ),
            {
                "e": exercise_id,
                "name": request.name.strip(),
                "implement": request.implement,
                "gym": request.gym_id,
                "increment": increment,
                "weight": weight,
            },
        )
    ).one()
    await links.variant_changed(connection, str(row.id))
    return Variant(
        id=str(row.id),
        exercise_id=exercise_id,
        name=request.name.strip(),
        implement=request.implement,
        gym_id=request.gym_id,
        min_increment=increment,
        index_weight=weight,
    )


class GymIn(BaseModel):
    name: Name
    active: bool = True


async def create_gym(connection: AsyncConnection, request: GymIn) -> Gym:
    taken = await connection.scalar(
        text("select 1 from training.training_gym where lower(name) = lower(:name)"),
        {"name": request.name.strip()},
    )
    if taken:
        raise Conflict(f"ya existe un centro que se llama «{request.name.strip()}»")
    gym_id = await connection.scalar(
        text(
            "insert into training.training_gym (name, active) values (:name, :active) returning id"
        ),
        {"name": request.name.strip(), "active": request.active},
    )
    return Gym(id=str(gym_id), name=request.name.strip(), active=request.active)


async def update_gym(connection: AsyncConnection, gym_id: str, request: GymIn) -> Gym:
    found = await connection.scalar(
        text(
            "update training.training_gym set name = :name, active = :active where id = :id returning id"
        ),
        {"name": request.name.strip(), "active": request.active, "id": gym_id},
    )
    if found is None:
        raise NotFound(gym_id)
    return Gym(id=gym_id, name=request.name.strip(), active=request.active)


class SettingsIn(BaseModel):
    weekly_goal: Annotated[int, Field(ge=1, le=14)]


class BodyweightIn(BaseModel):
    kg: Annotated[float, Field(gt=20, lt=400)]


async def update_bodyweight(
    connection: AsyncConnection, request: BodyweightIn, today: date
) -> plan.Settings:
    await connection.execute(
        text(
            "insert into training.training_bodyweight (day, kg) values (:day, :kg) "
            "on conflict (user_id, day) do update set kg = excluded.kg"
        ),
        {"day": today, "kg": round(request.kg, 2)},
    )
    return await plan.settings(connection)


async def update_settings(connection: AsyncConnection, request: SettingsIn) -> plan.Settings:
    await connection.execute(
        text(
            "insert into training.training_settings (weekly_goal) values (:goal) "
            "on conflict (user_id) do update set weekly_goal = excluded.weekly_goal, "
            "updated_at = now()"
        ),
        {"goal": request.weekly_goal},
    )
    return await plan.settings(connection)


class Version(BaseModel):
    id: str
    number: int
    valid_from: date | None
    published_at: datetime | None
    days: list[plan.Day]


class PlanHead(BaseModel):
    id: str
    name: str


class Editor(BaseModel):
    plan: PlanHead | None
    published: Version | None
    draft: Version | None
    rotation_version: int | None


async def _version(connection: AsyncConnection, where: str, plan_id: str) -> Version | None:
    row = (
        await connection.execute(
            text(
                "select id, number, valid_from, published_at from training.training_plan_version "
                f"where plan_id = :plan and {where} order by number desc limit 1"
            ),
            {"plan": plan_id},
        )
    ).one_or_none()
    if row is None:
        return None
    return Version(
        id=str(row.id),
        number=row.number,
        valid_from=row.valid_from,
        published_at=row.published_at,
        days=await plan.version_days(connection, str(row.id)),
    )


async def _active_plan(connection: AsyncConnection) -> PlanHead | None:
    row = (
        await connection.execute(text("select id, name from training.training_plan where active"))
    ).one_or_none()
    return PlanHead(id=str(row.id), name=row.name) if row else None


async def editor(connection: AsyncConnection) -> Editor:
    head = await _active_plan(connection)
    rotation_version = await connection.scalar(
        text(
            "select v.number from training.training_rotation r "
            "join training.training_plan_version v on v.id = r.plan_version_id where r.status = 'open'"
        )
    )
    if head is None:
        return Editor(plan=None, published=None, draft=None, rotation_version=rotation_version)
    return Editor(
        plan=head,
        published=await _version(connection, "published_at is not null", head.id),
        draft=await _version(connection, "published_at is null", head.id),
        rotation_version=rotation_version,
    )


class PlanIn(BaseModel):
    name: Name


async def create_plan(connection: AsyncConnection, request: PlanIn) -> Editor:
    if await _active_plan(connection):
        raise Conflict("ya hay un plan activo; se edita, no se crea otro")
    plan_id = await connection.scalar(
        text("insert into training.training_plan (name, active) values (:name, true) returning id"),
        {"name": request.name.strip()},
    )
    await connection.execute(
        text("insert into training.training_plan_version (plan_id, number) values (:plan, 1)"),
        {"plan": plan_id},
    )
    return await editor(connection)


async def rename_plan(connection: AsyncConnection, request: PlanIn) -> Editor:
    updated = await connection.scalar(
        text("update training.training_plan set name = :name where active returning id"),
        {"name": request.name.strip()},
    )
    if updated is None:
        raise NotFound("plan")
    return await editor(connection)


class SlotIn(BaseModel):
    target_sets: Annotated[int, Field(ge=1, le=20)]
    rep_min: Annotated[int, Field(ge=1, le=100)]
    rep_max: Annotated[int, Field(ge=1, le=100)]
    allow_both: bool = False
    variant_ids: Annotated[list[str], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def _range(self) -> SlotIn:
        if self.rep_min > self.rep_max:
            raise ValueError("el mínimo de repeticiones no puede pasar del máximo")
        if len(set(self.variant_ids)) != len(self.variant_ids):
            raise ValueError("la misma variante dos veces en un ejercicio")
        return self


class DayIn(BaseModel):
    name: Name
    kind: plan.DayKind
    slots: Annotated[list[SlotIn], Field(max_length=30)] = []


class DraftIn(BaseModel):
    days: Annotated[list[DayIn], Field(max_length=14)]


async def _draft_id(connection: AsyncConnection) -> str | None:
    found = await connection.scalar(
        text(
            "select v.id from training.training_plan_version v "
            "join training.training_plan p on p.id = v.plan_id "
            "where p.active and v.published_at is null"
        )
    )
    return str(found) if found else None


async def _write_days(connection: AsyncConnection, version_id: str, days: list[DayIn]) -> None:
    await connection.execute(
        text("delete from training.training_plan_day where plan_version_id = :v"), {"v": version_id}
    )
    for day_position, day in enumerate(days, start=1):
        day_id = await connection.scalar(
            text(
                "insert into training.training_plan_day (plan_version_id, name, kind, position) "
                "values (:v, :name, :kind, :position) returning id"
            ),
            {"v": version_id, "name": day.name.strip(), "kind": day.kind, "position": day_position},
        )
        for slot_position, slot in enumerate(day.slots, start=1):
            slot_id = await connection.scalar(
                text(
                    "insert into training.training_plan_slot "
                    "(plan_day_id, position, target_sets, rep_min, rep_max, allow_both) "
                    "values (:d, :position, :sets, :min, :max, :both) returning id"
                ),
                {
                    "d": day_id,
                    "position": slot_position,
                    "sets": slot.target_sets,
                    "min": slot.rep_min,
                    "max": slot.rep_max,
                    "both": slot.allow_both and len(slot.variant_ids) > 1,
                },
            )
            for priority, variant_id in enumerate(slot.variant_ids, start=1):
                await connection.execute(
                    text(
                        "insert into training.training_plan_slot_option "
                        "(plan_slot_id, variant_id, priority) values (:s, cast(:v as uuid), :p)"
                    ),
                    {"s": slot_id, "v": variant_id, "p": priority},
                )


def _as_input(days: list[plan.Day]) -> list[DayIn]:
    return [
        DayIn(
            name=day.name,
            kind=day.kind,
            slots=[
                SlotIn(
                    target_sets=slot.target_sets,
                    rep_min=slot.rep_min,
                    rep_max=slot.rep_max,
                    allow_both=slot.allow_both,
                    variant_ids=[option.variant_id for option in slot.options],
                )
                for slot in day.slots
                if slot.options
            ],
        )
        for day in days
    ]


async def open_draft(connection: AsyncConnection) -> Editor:
    current = await editor(connection)
    if current.plan is None:
        raise NotFound("plan")
    if current.draft is not None:
        return current
    number = await connection.scalar(
        text(
            "select coalesce(max(number), 0) + 1 from training.training_plan_version where plan_id = :p"
        ),
        {"p": current.plan.id},
    )
    draft_id = await connection.scalar(
        text(
            "insert into training.training_plan_version (plan_id, number) values (:p, :n) returning id"
        ),
        {"p": current.plan.id, "n": number},
    )
    if current.published is not None:
        await _write_days(connection, str(draft_id), _as_input(current.published.days))
    return await editor(connection)


async def save_draft(connection: AsyncConnection, request: DraftIn) -> Editor:
    draft_id = await _draft_id(connection)
    if draft_id is None:
        raise Conflict("no hay borrador; empieza a editar el plan primero")
    await _write_days(connection, draft_id, request.days)
    return await editor(connection)


async def discard_draft(connection: AsyncConnection) -> Editor:
    draft_id = await _draft_id(connection)
    if draft_id is None:
        return await editor(connection)
    await connection.execute(
        text("delete from training.training_plan_version where id = :id"), {"id": draft_id}
    )
    return await editor(connection)


async def publish_draft(connection: AsyncConnection, now: datetime | None = None) -> Editor:
    current = await editor(connection)
    draft = current.draft
    if draft is None:
        raise Conflict("no hay borrador que publicar")
    if not draft.days:
        raise Conflict("el plan necesita al menos un día")
    empty = [day.name for day in draft.days if not day.slots]
    if empty:
        raise Conflict(f"cada día necesita al menos un ejercicio: {', '.join(empty)}")
    moment = now or datetime.now(UTC)
    await connection.execute(
        text(
            "update training.training_plan_version set published_at = :at, valid_from = :day "
            "where id = :id"
        ),
        {"at": moment, "day": local_day(moment), "id": draft.id},
    )
    return await editor(connection)
