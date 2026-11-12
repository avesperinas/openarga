from __future__ import annotations

import asyncio
import sys
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import as_user, from_environment
from training.db import engine

GYM = "Gimnasio de ejemplo"

EXERCISES = [
    (
        "Press banca",
        "horizontal_push",
        "external",
        None,
        {"chest": 1.0, "triceps": 0.5, "front_delts": 0.5},
    ),
    ("Press militar", "vertical_push", "external", None, {"front_delts": 1.0, "triceps": 0.5}),
    ("Fondos", "vertical_push", "weighted_bodyweight", 0.95, {"chest": 1.0, "triceps": 0.5}),
    ("Remo", "horizontal_pull", "external", None, {"upper_back": 1.0, "lats": 0.5, "biceps": 0.5}),
    ("Dominadas", "vertical_pull", "weighted_bodyweight", 1.0, {"lats": 1.0, "biceps": 0.5}),
    ("Curl de bíceps", "isolation", "external", None, {"biceps": 1.0}),
    ("Sentadilla", "knee_dominant", "external", None, {"quads": 1.0, "glutes": 0.5}),
    (
        "Peso muerto rumano",
        "hip_dominant",
        "external",
        None,
        {"hamstrings": 1.0, "glutes": 0.5, "lower_back": 0.5},
    ),
]

VARIANTS = [
    ("Press banca", "Press banca con barra", "barbell", 2.5, 3),
    ("Press banca", "Press banca en máquina", "machine", 5, 2),
    ("Press militar", "Press militar con mancuernas", "dumbbell", 2, 2),
    ("Fondos", "Fondos lastrados", "bodyweight", 2.5, 2),
    ("Remo", "Remo con barra", "barbell", 2.5, 3),
    ("Dominadas", "Dominadas lastradas", "bodyweight", 2.5, 3),
    ("Curl de bíceps", "Curl en polea", "cable", 5, 1),
    ("Sentadilla", "Sentadilla en Smith", "smith", 2.5, 3),
    ("Sentadilla", "Prensa", "machine", 5, 2),
    ("Peso muerto rumano", "Peso muerto rumano con barra", "barbell", 2.5, 3),
]

DAYS = [
    (
        "Push",
        "push",
        [
            (4, 6, 10, False, ["Press banca con barra", "Press banca en máquina"]),
            (3, 8, 12, False, ["Press militar con mancuernas"]),
            (3, 6, 12, False, ["Fondos lastrados"]),
        ],
    ),
    (
        "Pull",
        "pull",
        [
            (4, 6, 10, False, ["Remo con barra"]),
            (4, 5, 10, False, ["Dominadas lastradas"]),
            (3, 10, 15, False, ["Curl en polea"]),
        ],
    ),
    (
        "Leg",
        "leg",
        [
            (4, 6, 10, True, ["Sentadilla en Smith", "Prensa"]),
            (3, 8, 12, False, ["Peso muerto rumano con barra"]),
        ],
    ),
]


async def seed(connection: AsyncConnection) -> None:
    if await connection.scalar(text("select 1 from training.training_plan limit 1")):
        raise RuntimeError("ya hay un plan: el seed sintético no se mezcla con datos de nadie")

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
            "seed fallido: falta ARGA_USER_ID, la persona dueña del plan sintético", file=sys.stderr
        )
        return 2
    try:
        with as_user(person):
            asyncio.run(_main())
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"seed fallido: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("plan sintético cargado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
