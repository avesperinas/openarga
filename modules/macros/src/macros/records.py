from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from macros import intake, summary
from macros.common import today, zone

APP = "macros"
PROPERTIES = (
    ("kcal", "kcal", 0),
    ("protein", "protein_g", 1),
    ("carbs", "carbs_g", 1),
    ("fat", "fat_g", 1),
    ("fiber", "fiber_g", 1),
)
NAMES = {"protein": "protein", "carbs": "carbs", "fat": "fat"}


def _number(value: float) -> str:
    return f"{value:,.0f}"


def _trimmed(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _amount(item: intake.Item) -> str:
    return f"{_trimmed(item.quantity)} {item.unit}"


def _totals(nutrients: dict[str, float]) -> str:
    parts = []
    if "kcal" in nutrients:
        parts.append(f"{_number(nutrients['kcal'])} kcal")
    for key in ("protein", "carbs", "fat"):
        if key in nutrients:
            parts.append(f"{_number(nutrients[key])} g {NAMES[key]}")
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
        when = entry.eaten_at.astimezone(zone()).strftime("%H:%M")
        things = ", ".join(f"{item.name} ({_amount(item)})" for item in entry.items)
        kcal = entry.nutrients.get("kcal")
        lines.append(f"- {when} · {things}" + (f" · {_number(kcal)} kcal" if kcal else ""))
    return contracts.record(
        id=f"day:{on.isoformat()}",
        title="Meals",
        kind="Day",
        href=f"/macros/day/{on.isoformat()}",
        day=on,
        properties=properties,
        body=write.sections(_totals(nutrients), "\n".join(lines)),
    )


def target(found: summary.Target) -> dict[str, Any]:
    values = {
        "kcal": found.kcal,
        "protein_g": found.protein,
        "carbs_g": found.carbs,
        "fat_g": found.fat,
    }
    lines = [
        f"- {label}: {_trimmed(value)} {unit}"
        for label, value, unit in (
            ("Energy", found.kcal, "kcal"),
            ("Protein", found.protein, "g"),
            ("Carbs", found.carbs, "g"),
            ("Fat", found.fat, "g"),
        )
        if value is not None
    ]
    return contracts.record(
        id="target",
        title="Target",
        kind="Target",
        href="/macros/goals",
        properties={
            "since": found.valid_from.isoformat(),
            **{key: value for key, value in values.items() if value is not None},
        },
        body=write.sections(
            f"What you aim to eat each day since {found.valid_from.isoformat()}.",
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
