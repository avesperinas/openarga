from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from macros import intake, summary
from macros.common import today

APP = "macros"
MADRID = ZoneInfo("Europe/Madrid")
PROPERTIES = (
    ("kcal", "kcal", 0),
    ("protein", "proteina_g", 1),
    ("carbs", "hidratos_g", 1),
    ("fat", "grasa_g", 1),
    ("fiber", "fibra_g", 1),
)
NAMES = {"protein": "proteína", "carbs": "hidratos", "fat": "grasa"}


def _amount(item: intake.Item) -> str:
    return f"{write.trimmed(item.quantity)} {item.unit}"


def _totals(nutrients: dict[str, float]) -> str:
    parts = []
    if "kcal" in nutrients:
        parts.append(f"{write.number(nutrients['kcal'])} kcal")
    for key in ("protein", "carbs", "fat"):
        if key in nutrients:
            parts.append(f"{write.number(nutrients[key])} g {NAMES[key]}")
    return " · ".join(parts)


def day(on: date, entries: list[intake.Entry]) -> dict[str, Any]:
    nutrients: dict[str, float] = defaultdict(float)
    for entry in entries:
        for key, value in entry.nutrients.items():
            nutrients[key] += value
    properties = {
        name: round(nutrients[key], digits) if digits else round(nutrients[key])
        for key, name, digits in PROPERTIES
        if key in nutrients
    }
    lines = []
    for entry in sorted(entries, key=lambda one: one.eaten_at):
        when = entry.eaten_at.astimezone(MADRID).strftime("%H:%M")
        things = ", ".join(f"{item.name} ({_amount(item)})" for item in entry.items)
        kcal = entry.nutrients.get("kcal")
        lines.append(f"- {when} · {things}" + (f" · {write.number(kcal)} kcal" if kcal else ""))
    return contracts.record(
        id=f"day:{on.isoformat()}",
        title="Comidas",
        kind="Día",
        href=f"/macros/dia/{on.isoformat()}",
        day=on,
        properties=properties,
        body=write.sections(_totals(nutrients), "\n".join(lines)),
    )


def target(found: summary.Target) -> dict[str, Any]:
    values = {
        "kcal": found.kcal,
        "proteina_g": found.protein,
        "hidratos_g": found.carbs,
        "grasa_g": found.fat,
    }
    lines = [
        f"- {label}: {write.trimmed(value)} {unit}"
        for label, value, unit in (
            ("Energía", found.kcal, "kcal"),
            ("Proteína", found.protein, "g"),
            ("Hidratos", found.carbs, "g"),
            ("Grasa", found.fat, "g"),
        )
        if value is not None
    ]
    return contracts.record(
        id="target",
        title="Objetivo",
        kind="Objetivo",
        href="/macros/objetivo",
        properties={
            "desde": found.valid_from.isoformat(),
            **{key: value for key, value in values.items() if value is not None},
        },
        body=write.sections(
            f"Lo que te propones comer cada día desde el {write.long_date(found.valid_from)}.",
            "\n".join(lines),
        ),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    by_day: dict[date, list[intake.Entry]] = defaultdict(list)
    for entry in await intake.entries(connection, date.min, date.max):
        by_day[entry.day].append(entry)
    found = [day(on, entries) for on, entries in sorted(by_day.items())]
    current = await summary.target_on(connection, today())
    if current is not None:
        found.append(target(current))
    return found
