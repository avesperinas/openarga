from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona, localizer
from macros import goals, intake, templates

say = localizer(Path(__file__).parent / "seed" / "i18n")

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-0000000ac705")
DAYS = 18 * 30
DAILY = 90

TARGET = text("""
    insert into macros.macros_target (id, valid_from, kcal, protein, carbs, fat)
    values (:id, :valid_from, :kcal, :protein, :carbs, :fat)
    on conflict do nothing
""")

ENTRY = text("""
    insert into macros.macros_entry (id, eaten_at, tz, day, said, origin)
    values (:id, :eaten_at, :tz, :day, :said, 'app')
    on conflict do nothing
""")

ITEM = text("""
    insert into macros.macros_item (id, entry_id, position, kind, name, quantity, unit, nutrients)
    values (:id, :entry, :position, :kind, :name, :quantity, :unit, cast(:nutrients as jsonb))
    on conflict do nothing
""")

COMPLETE = text("""
    insert into macros.macros_day_complete (day, marked_at) values (:day, :marked_at)
    on conflict do nothing
""")

MEALS = (
    ("breakfast", time(8, 15), 0.22, (0.20, 0.55, 0.25)),
    ("lunch", time(14, 30), 0.40, (0.25, 0.45, 0.30)),
    ("snack", time(18, 0), 0.10, (0.15, 0.55, 0.30)),
    ("dinner", time(21, 15), 0.28, (0.30, 0.35, 0.35)),
)
NAMES = {
    "alex": {
        "breakfast": ("Oats with milk and fruit", "Toast with olive oil and tomato",
                      "Protein smoothie", "Avocado toast"),
        "lunch": ("Lentil stew", "Chicken curry", "Greek salad", "Tuna salad", "Pasta with tomato"),
        "snack": ("Yogurt and nuts", "Apple and cheese", "Hummus and carrots"),
        "dinner": ("Baked salmon with vegetables", "Lemon chicken traybake", "Beef stew",
                   "Veggie stir-fry", "Fish tacos"),
    },
    "sam": {
        "breakfast": ("Pancakes", "Shakshuka", "Overnight oats", "Avocado toast"),
        "lunch": ("Chickpea curry", "Gazpacho", "Spanish lentils with chorizo", "Greek salad"),
        "snack": ("Yogurt and nuts", "Apple and cheese", "Oat cookies"),
        "dinner": ("Potato omelette and salad", "Mushroom risotto", "Hake in green sauce",
                   "Ratatouille", "Pumpkin soup"),
    },
}  # fmt: skip
TEMPLATES = {
    "alex": (
        ("Usual breakfast", "Oats with milk and fruit", 520, (28, 70, 14), "08:15"),
        ("Post-workout shake", "Protein smoothie", 380, (40, 38, 8), None),
        ("Lunch box", "Chicken curry", 780, (48, 80, 24), None),
    ),
    "sam": (
        ("Usual breakfast", "Overnight oats", 410, (18, 58, 12), "08:00"),
        ("Afternoon snack", "Yogurt and nuts", 240, (10, 18, 14), None),
        ("Quick dinner", "Veggie stir-fry", 560, (26, 62, 18), None),
    ),
}


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.key}:{key}")


def _logged(back: int) -> bool:
    return back <= DAILY or back % 7 in (1, 4)


def _nutrients(kcal: float, split: tuple[float, float, float]) -> dict[str, float]:
    protein, carbs, fat = split
    return {
        "kcal": round(kcal),
        "protein": round(kcal * protein / 4, 1),
        "carbs": round(kcal * carbs / 4, 1),
        "fat": round(kcal * fat / 9, 1),
    }


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    zone = ZoneInfo(persona.timezone)
    alex = persona.key == "alex"
    daily = 2400 if alex else 1900
    await connection.execute(
        TARGET,
        {
            "id": _id(persona, "target"),
            "valid_from": today - timedelta(days=DAYS),
            "kcal": daily,
            "protein": 150 if alex else 100,
            "carbs": 270 if alex else 220,
            "fat": 80 if alex else 65,
        },
    )
    for back in range(DAYS, -1, -1):
        if not _logged(back):
            continue
        day = today - timedelta(days=back)
        meals = MEALS if back else MEALS[:2]
        for slot, (meal, at, share, split) in enumerate(meals):
            options = NAMES[persona.key][meal]
            name = options[(back + slot + (0 if alex else 1)) % len(options)]
            kcal = daily * share * (0.9 + ((back * 7 + slot) % 5) * 0.05)
            entry = _id(persona, f"entry-{back}-{meal}")
            eaten = datetime.combine(day, at, zone)
            await connection.execute(
                ENTRY,
                {
                    "id": entry,
                    "eaten_at": eaten,
                    "tz": persona.timezone,
                    "day": day,
                    "said": say(persona, name),
                },
            )
            await connection.execute(
                ITEM,
                {
                    "id": _id(persona, f"item-{back}-{meal}"),
                    "entry": entry,
                    "position": 1,
                    "kind": "quick",
                    "name": say(persona, name),
                    "quantity": round(kcal),
                    "unit": "kcal",
                    "nutrients": json.dumps(_nutrients(kcal, split)),
                },
            )
            if meal == "lunch":
                await connection.execute(
                    ITEM,
                    {
                        "id": _id(persona, f"water-{back}"),
                        "entry": entry,
                        "position": 2,
                        "kind": "water",
                        "name": say(persona, "Water"),
                        "quantity": 500,
                        "unit": "ml",
                        "nutrients": json.dumps({"water": 500}),
                    },
                )
        if back:
            await connection.execute(
                COMPLETE,
                {"day": day, "marked_at": datetime.combine(day, time(22, 30), zone)},
            )
    await _plan(connection, persona, today)


async def _plan(connection: AsyncConnection, persona: Persona, today: date) -> None:
    alex = persona.key == "alex"
    for nutrient, low, high in (
        ("protein", 150 if alex else 100, None),
        ("fiber", 30, None),
        ("sodium", None, 2300),
        ("sugars", None, 50),
    ):
        await goals.set_goal(
            connection,
            goals.GoalIn(
                nutrient=nutrient, min=low, max=high, valid_from=today - timedelta(days=DAYS)
            ),
        )
    training = (0, 2, 4) if alex else (1, 3, 5)
    for back in range(0, 30):
        day = today - timedelta(days=back)
        await goals.set_day_kind(
            connection, day, "training" if day.weekday() in training else "rest"
        )
    for name, said, kcal, (protein, carbs, fat), daily_at in TEMPLATES[persona.key]:
        await templates.save(
            connection,
            templates.TemplateIn(
                name=say(persona, name),
                said=say(persona, said),
                items=[
                    intake.ItemIn(
                        kind="quick",
                        name=say(persona, said),
                        quantity=kcal,
                        unit="kcal",
                        quick=intake.QuickMacros(protein=protein, carbs=carbs, fat=fat),
                    )
                ],
                daily_at=time.fromisoformat(daily_at) if daily_at else None,
            ),
        )
