from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona, localizer
from training import agenda, workouts
from training import seed as catalogue

say = localizer(Path(__file__).parent / "seed" / "i18n")

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-000000071a17")
WEEKS = 78
GYMS = {"alex": "Iron Yard Gym", "sam": "Pulse Fitness Studio"}
ANCHOR = date(2024, 1, 1)

ACTIVITIES = {
    "alex": (
        (1, "RUNNING", "Running", 18 * 60 + 30, 42, lambda week: week % 3 != 2),
        (5, "PADEL", "Padel", 10 * 60, 75, lambda week: week % 2 == 0),
    ),
    "sam": (
        (0, "YOGA", "Yoga", 19 * 60, 55, lambda week: True),
        (3, "SWIMMING", "Swimming", 7 * 60 + 30, 40, lambda week: week % 2 == 1),
    ),
}

ACTIVITY_TYPE = text("""
    insert into training.training_activity_type (id, name, band_kinds)
    values (:id, :name, :kinds)
    on conflict do nothing
""")

ACTIVITY = text("""
    insert into training.training_activity
        (id, activity_type_id, day, start_time, duration_seconds, band_id, notes)
    values (:id, :type, :day, :start, :seconds, :band, :notes)
    on conflict do nothing
""")

GYM = text("""
    insert into training.training_gym (id, name) values (:id, :name)
    on conflict do nothing
""")

EXERCISE = text("""
    insert into training.training_exercise (id, name, key, pattern, load_type, bodyweight_factor)
    values (:id, :name, :key, :pattern, :load_type, :factor)
    on conflict do nothing
""")

MUSCLE = text("""
    insert into training.training_exercise_muscle (exercise_id, muscle_id, contribution)
    values (:exercise, :muscle, :contribution)
    on conflict do nothing
""")

VARIANT = text("""
    insert into training.training_variant
        (id, exercise_id, name, key, implement, gym_id, min_increment, index_weight)
    values (:id, :exercise, :name, :key, :implement, :gym, :increment, :weight)
    on conflict do nothing
""")

PLAN = text("""
    insert into training.training_plan (id, name, active) values (:id, :name, true)
    on conflict do nothing
""")

VERSION = text("""
    insert into training.training_plan_version (id, plan_id, number)
    values (:id, :plan, 1)
    on conflict do nothing
""")

PUBLISHED = text(
    "select published_at is not null from training.training_plan_version where id = :id"
)

PUBLISH = text("""
    update training.training_plan_version set valid_from = :valid_from, published_at = :published_at
    where id = :id and published_at is null
""")

DAY = text("""
    insert into training.training_plan_day (id, plan_version_id, name, kind, position)
    values (:id, :version, :name, :kind, :position)
    on conflict do nothing
""")

SLOT = text("""
    insert into training.training_plan_slot
        (id, plan_day_id, position, target_sets, rep_min, rep_max, allow_both)
    values (:id, :day, :position, :sets, :rep_min, :rep_max, :both)
    on conflict do nothing
""")

OPTION = text("""
    insert into training.training_plan_slot_option (plan_slot_id, variant_id, priority)
    values (:slot, :variant, :priority)
    on conflict do nothing
""")

OPEN_ROTATION = text("""
    insert into training.training_rotation (id, plan_version_id, number, status, opened_at)
    values (:id, :version, :number, 'open', :opened_at)
    on conflict do nothing
""")

ROTATION = text("""
    insert into training.training_rotation
        (id, plan_version_id, number, status, opened_at, closed_at)
    values (:id, :version, :number, 'complete', :opened_at, :closed_at)
    on conflict do nothing
""")

SESSION = text("""
    insert into training.training_session
        (id, rotation_id, plan_version_id, plan_day_id, gym_id, day, started_at, ended_at,
         duration_seconds)
    values (:id, :rotation, :version, :day_id, :gym, :day, :started_at, :ended_at, :seconds)
    on conflict do nothing
""")

SESSION_EXERCISE = text("""
    insert into training.training_session_exercise
        (id, session_id, plan_slot_id, variant_id, position)
    values (:id, :session, :slot, :variant, :position)
    on conflict do nothing
""")

SET = text("""
    insert into training.training_set_log
        (id, session_exercise_id, number, reps, weight, added_load, completed, confirmed_at)
    values (:id, :exercise, :number, :reps, :weight, :added_load, true, :confirmed_at)
    on conflict do nothing
""")

START_KG = {
    "barbell_bench_press": 60,
    "machine_chest_press": 50,
    "dumbbell_overhead_press": 16,
    "weighted_dips": 5,
    "barbell_row": 55,
    "weighted_pull_ups": 2.5,
    "cable_curl": 20,
    "smith_machine_squat": 70,
    "leg_press": 120,
    "barbell_romanian_deadlift": 70,
}
WEIGHTED = {"weighted_dips", "weighted_pull_ups"}


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.seed_key}:{key}")


def _load(key: str, week: int, persona: Persona, increment: float) -> float:
    scale = 1.0 if persona.key == "alex" else 0.7
    steps = week // 3
    value = START_KG[key] * scale + steps * increment
    return round(value / increment) * increment


async def _catalogue(connection: AsyncConnection, persona: Persona) -> tuple[UUID, dict]:
    gym = _id(persona, "gym")
    await connection.execute(GYM, {"id": gym, "name": GYMS[persona.key]})
    exercises = {}
    for name, pattern, load_type, factor, muscles in catalogue.EXERCISES:
        key = catalogue.key_of(name)
        exercises[name] = _id(persona, f"exercise-{key}")
        await connection.execute(
            EXERCISE,
            {
                "id": exercises[name],
                "name": name,
                "key": key,
                "pattern": pattern,
                "load_type": load_type,
                "factor": factor,
            },
        )
        for muscle, contribution in muscles.items():
            await connection.execute(
                MUSCLE,
                {"exercise": exercises[name], "muscle": muscle, "contribution": contribution},
            )
    variants = {}
    for exercise, name, implement, increment, weight in catalogue.VARIANTS:
        key = catalogue.key_of(name)
        variants[name] = (_id(persona, f"variant-{key}"), key, increment)
        await connection.execute(
            VARIANT,
            {
                "id": variants[name][0],
                "exercise": exercises[exercise],
                "name": name,
                "key": key,
                "implement": implement,
                "gym": gym,
                "increment": increment,
                "weight": weight,
            },
        )
    return gym, variants


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    zone = ZoneInfo(persona.timezone)
    alex = persona.key == "alex"
    gym, variants = await _catalogue(connection, persona)
    start = today - timedelta(weeks=WEEKS, days=today.weekday())
    plan, version = _id(persona, "plan"), _id(persona, "version")
    await connection.execute(PLAN, {"id": plan, "name": say(persona, "Push Pull Leg")})
    await connection.execute(VERSION, {"id": version, "plan": plan})
    published = await connection.scalar(PUBLISHED, {"id": version})
    days = []
    for position, (name, kind, slots) in enumerate(catalogue.DAYS, start=1):
        day_id = _id(persona, f"day-{kind}")
        if not published:
            await connection.execute(
                DAY,
                {
                    "id": day_id,
                    "version": version,
                    "name": say(persona, name),
                    "kind": kind,
                    "position": position,
                },
            )
        planned = []
        for slot_position, (sets, rep_min, rep_max, both, options) in enumerate(slots, start=1):
            slot = _id(persona, f"slot-{kind}-{slot_position}")
            planned.append((slot, variants[options[0]], sets, rep_min, rep_max))
            if published:
                continue
            await connection.execute(
                SLOT,
                {
                    "id": slot,
                    "day": day_id,
                    "position": slot_position,
                    "sets": sets,
                    "rep_min": rep_min,
                    "rep_max": rep_max,
                    "both": both,
                },
            )
            for priority, option in enumerate(options, start=1):
                await connection.execute(
                    OPTION, {"slot": slot, "variant": variants[option][0], "priority": priority}
                )
        days.append((day_id, kind, planned))

    await connection.execute(
        PUBLISH,
        {
            "id": version,
            "valid_from": start,
            "published_at": datetime.combine(start, time(9), zone),
        },
    )
    offsets = (0, 2, 4) if alex else (1, 3, 5)
    for week in range(WEEKS + 1):
        monday = start + timedelta(weeks=week)
        if monday > today:
            break
        current = monday + timedelta(days=6) >= today
        rotation = _id(persona, f"rotation-{week}")
        opened = datetime.combine(monday, time(7), zone)
        if current:
            await connection.execute(
                OPEN_ROTATION,
                {"id": rotation, "version": version, "number": week + 1, "opened_at": opened},
            )
        else:
            await connection.execute(
                ROTATION,
                {
                    "id": rotation,
                    "version": version,
                    "number": week + 1,
                    "opened_at": opened,
                    "closed_at": opened + timedelta(days=offsets[-1], hours=12),
                },
            )
        for (day_id, kind, planned), offset in zip(days, offsets, strict=True):
            day = monday + timedelta(days=offset)
            if day >= today:
                continue
            if not alex and week % 9 == 4 and kind == "leg":
                continue
            if week % 13 == 6 and kind == "push":
                continue
            await _session(connection, persona, zone, version, rotation, gym, day_id, kind,
                           planned, day, week)  # fmt: skip

    await _activities(connection, persona, zone, start, today)
    await agenda.backfill(connection)
    await agenda.backfill_activities(connection)
    await workouts.backfill(connection)


async def _session(
    connection, persona, zone, version, rotation, gym, day_id, kind, planned, day, week
) -> None:
    started = datetime.combine(day, time(19 if persona.key == "alex" else 8, 0), zone)
    session = _id(persona, f"session-{week}-{kind}")
    minutes = 15 * len(planned) + 10
    await connection.execute(
        SESSION,
        {
            "id": session,
            "rotation": rotation,
            "version": version,
            "day_id": day_id,
            "gym": gym,
            "day": day,
            "started_at": started,
            "ended_at": started + timedelta(minutes=minutes),
            "seconds": minutes * 60,
        },
    )
    at = started
    for position, (slot, (variant, key, increment), sets, rep_min, rep_max) in enumerate(
        planned, start=1
    ):
        exercise = _id(persona, f"session-{week}-{kind}-{position}")
        await connection.execute(
            SESSION_EXERCISE,
            {
                "id": exercise,
                "session": session,
                "slot": slot,
                "variant": variant,
                "position": position,
            },
        )
        load = _load(key, week, persona, increment)
        reps = rep_min + (week % 3) * max(1, (rep_max - rep_min) // 3)
        for number in range(1, sets + 1):
            at += timedelta(minutes=3)
            await connection.execute(
                SET,
                {
                    "id": _id(persona, f"set-{week}-{kind}-{position}-{number}"),
                    "exercise": exercise,
                    "number": number,
                    "reps": max(rep_min, min(rep_max, reps - (number > 2))),
                    "weight": None if key in WEIGHTED else load,
                    "added_load": load if key in WEIGHTED else None,
                    "confirmed_at": at,
                },
            )


async def _activities(connection, persona, zone, start: date, today: date) -> None:
    types = {}
    for _, kind, name, _, _, _ in ACTIVITIES[persona.key]:
        types[kind] = _id(persona, f"activity-type-{kind}")
        await connection.execute(
            ACTIVITY_TYPE, {"id": types[kind], "name": say(persona, name), "kinds": [kind]}
        )
    day = start
    while day < today:
        for weekday, kind, _name, minute, length, when in ACTIVITIES[persona.key]:
            if day.weekday() != weekday or not when((day - ANCHOR).days // 7):
                continue
            await connection.execute(
                ACTIVITY,
                {
                    "id": _id(persona, f"activity-{kind}-{day}"),
                    "type": types[kind],
                    "day": day,
                    "start": time(minute // 60, minute % 60),
                    "seconds": length * 60,
                    "band": f"band-{kind.lower()}-{day.isoformat()}",
                    "notes": None,
                },
            )
        day += timedelta(days=1)
