from __future__ import annotations

import asyncio
import sys
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import as_user, from_environment
from training.db import engine

GYM = "Sample gym"

EXERCISES = [
    (
        "Bench press",
        "horizontal_push",
        "external",
        None,
        {"chest": 1.0, "triceps": 0.5, "front_delts": 0.5},
    ),
    ("Overhead press", "vertical_push", "external", None, {"front_delts": 1.0, "triceps": 0.5}),
    ("Dips", "vertical_push", "weighted_bodyweight", 0.95, {"chest": 1.0, "triceps": 0.5}),
    ("Row", "horizontal_pull", "external", None, {"upper_back": 1.0, "lats": 0.5, "biceps": 0.5}),
    ("Pull-ups", "vertical_pull", "weighted_bodyweight", 1.0, {"lats": 1.0, "biceps": 0.5}),
    ("Biceps curl", "isolation", "external", None, {"biceps": 1.0}),
    ("Squat", "knee_dominant", "external", None, {"quads": 1.0, "glutes": 0.5}),
    (
        "Romanian deadlift",
        "hip_dominant",
        "external",
        None,
        {"hamstrings": 1.0, "glutes": 0.5, "lower_back": 0.5},
    ),
]

VARIANTS = [
    ("Bench press", "Barbell bench press", "barbell", 2.5, 3),
    ("Bench press", "Machine chest press", "machine", 5, 2),
    ("Overhead press", "Dumbbell overhead press", "dumbbell", 2, 2),
    ("Dips", "Weighted dips", "bodyweight", 2.5, 2),
    ("Row", "Barbell row", "barbell", 2.5, 3),
    ("Pull-ups", "Weighted pull-ups", "bodyweight", 2.5, 3),
    ("Biceps curl", "Cable curl", "cable", 5, 1),
    ("Squat", "Smith machine squat", "smith", 2.5, 3),
    ("Squat", "Leg press", "machine", 5, 2),
    ("Romanian deadlift", "Barbell Romanian deadlift", "barbell", 2.5, 3),
]

DAYS = [
    (
        "Push",
        "push",
        [
            (4, 6, 10, False, ["Barbell bench press", "Machine chest press"]),
            (3, 8, 12, False, ["Dumbbell overhead press"]),
            (3, 6, 12, False, ["Weighted dips"]),
        ],
    ),
    (
        "Pull",
        "pull",
        [
            (4, 6, 10, False, ["Barbell row"]),
            (4, 5, 10, False, ["Weighted pull-ups"]),
            (3, 10, 15, False, ["Cable curl"]),
        ],
    ),
    (
        "Leg",
        "leg",
        [
            (4, 6, 10, True, ["Smith machine squat", "Leg press"]),
            (3, 8, 12, False, ["Barbell Romanian deadlift"]),
        ],
    ),
]


async def seed(connection: AsyncConnection) -> None:
    if await connection.scalar(text("select 1 from training.training_plan limit 1")):
        raise RuntimeError(
            "there is already a plan: the synthetic seed does not mix with anyone's data"
        )

    gym = await connection.scalar(
        text("insert into training.training_gym (name) values (:name) returning id"), {"name": GYM}
    )
    exercises = {}
    for name, pattern, load_type, factor, muscles in EXERCISES:
        exercises[name] = await connection.scalar(
            text(
                "insert into training.training_exercise (name, pattern, load_type, bodyweight_factor) "
                "values (:name, :pattern, :load_type, :factor) returning id"
            ),
            {"name": name, "pattern": pattern, "load_type": load_type, "factor": factor},
        )
        for muscle, contribution in muscles.items():
            await connection.execute(
                text(
                    "insert into training.training_exercise_muscle "
                    "(exercise_id, muscle_id, contribution) values (:e, :m, :c)"
                ),
                {"e": exercises[name], "m": muscle, "c": contribution},
            )

    variants = {}
    for exercise, name, implement, increment, weight in VARIANTS:
        variants[name] = await connection.scalar(
            text(
                "insert into training.training_variant "
                "(exercise_id, name, implement, gym_id, min_increment, index_weight) "
                "values (:e, :name, :implement, :gym, :increment, :weight) returning id"
            ),
            {
                "e": exercises[exercise],
                "name": name,
                "implement": implement,
                "gym": gym,
                "increment": increment,
                "weight": weight,
            },
        )

    plan_id = await connection.scalar(
        text(
            "insert into training.training_plan (name, active) "
            "values ('Push Pull Leg', true) returning id"
        )
    )
    version = await connection.scalar(
        text(
            "insert into training.training_plan_version (plan_id, number) values (:p, 1) returning id"
        ),
        {"p": plan_id},
    )
    for position, (name, kind, slots) in enumerate(DAYS, start=1):
        day = await connection.scalar(
            text(
                "insert into training.training_plan_day (plan_version_id, name, kind, position) "
                "values (:v, :name, :kind, :position) returning id"
            ),
            {"v": version, "name": name, "kind": kind, "position": position},
        )
        for slot_position, (sets, rep_min, rep_max, both, options) in enumerate(slots, start=1):
            slot = await connection.scalar(
                text(
                    "insert into training.training_plan_slot "
                    "(plan_day_id, position, target_sets, rep_min, rep_max, allow_both) "
                    "values (:d, :p, :sets, :rmin, :rmax, :both) returning id"
                ),
                {
                    "d": day,
                    "p": slot_position,
                    "sets": sets,
                    "rmin": rep_min,
                    "rmax": rep_max,
                    "both": both,
                },
            )
            for priority, variant in enumerate(options, start=1):
                await connection.execute(
                    text(
                        "insert into training.training_plan_slot_option "
                        "(plan_slot_id, variant_id, priority) values (:s, :v, :p)"
                    ),
                    {"s": slot, "v": variants[variant], "p": priority},
                )

    await connection.execute(
        text(
            "update training.training_plan_version "
            "set published_at = now(), valid_from = :d where id = :v"
        ),
        {"d": date(2026, 9, 1), "v": version},
    )


async def _main() -> None:
    try:
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_training"'))
            await seed(connection)
    finally:
        await engine().dispose()


def main() -> int:
    person = from_environment()
    if person is None:
        print(
            "seed failed: ARGA_USER_ID is missing, the person who owns the synthetic plan",
            file=sys.stderr,
        )
        return 2
    try:
        with as_user(person):
            asyncio.run(_main())
    except Exception as error:  # noqa: BLE001 - turned into an exit code, not swallowed
        print(f"seed failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("synthetic plan loaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
