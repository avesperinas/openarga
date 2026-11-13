from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from recipes import foods, recipes

APP = "recipes"
PANTRY_LIMIT = 100_000


def _number(value: float) -> str:
    return f"{value:,.0f}"


def _trimmed(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _amount(one: recipes.IngredientOut) -> str:
    return f"{_trimmed(one.quantity)} {one.unit}".strip()


def recipe(found: recipes.Recipe) -> dict[str, Any]:
    kitchen = found.kitchen
    serving = found.nutrition.per_serving
    groups = []
    for group in found.groups:
        lines = "\n".join(
            f"- {one.name}: {_amount(one)}"
            + (f" · {one.note}" if one.note else "")
            + (" (optional)" if one.optional else "")
            for one in group.ingredients
        )
        groups.append(f"### {group.emoji} {group.name}\n\n{lines}")
    steps = "\n".join(
        f"{step.position + 1}. {step.text}"
        + (f" · {step.minutes} min" if step.minutes else "")
        + ("" if step.attended else " (unattended)")
        for step in sorted(kitchen.steps, key=lambda one: one.position)
    )
    macros = (
        f"{_number(serving.kcal)} kcal · {_trimmed(serving.protein)} g protein · "
        f"{_trimmed(serving.carbs)} g carbs · {_trimmed(serving.fat)} g fat"
    )
    if found.nutrition.uncertainty:
        macros += f"\n\n*{found.nutrition.uncertainty}*"
    lead = (
        f"For {found.servings} {'serving' if found.servings == 1 else 'servings'} · "
        f"{kitchen.total_minutes} min in all, {kitchen.active_minutes} attended · "
        f"version {found.version}"
    )
    properties: dict[str, Any] = {
        "servings": found.servings,
        "total_min": kitchen.total_minutes,
        "active_min": kitchen.active_minutes,
        "kcal_serving": round(serving.kcal),
        "protein_serving_g": round(serving.protein, 1),
        "carbs_serving_g": round(serving.carbs, 1),
        "fat_serving_g": round(serving.fat, 1),
        "version": found.version,
    }
    if found.tags:
        properties["tags"] = [tag.name for tag in found.tags]
    return contracts.record(
        id=f"recipe:{found.id}",
        title=found.name,
        kind="Recipe",
        href=f"/recipes/recipe/{found.id}",
        folder="Recipes",
        properties=properties,
        body=write.sections(
            lead + ".",
            found.note,
            "## Ingredients\n\n" + "\n\n".join(groups) if groups else None,
            f"## Steps\n\n{steps}" if steps else None,
            f"## Per serving\n\n{macros}",
        ),
    )


def pantry(found: list[foods.Food]) -> dict[str, Any]:
    rows = [
        [
            one.label,
            _number(one.macros.kcal),
            _trimmed(one.macros.protein),
            _trimmed(one.macros.carbs),
            _trimmed(one.macros.fat),
            one.source,
        ]
        for one in sorted(found, key=lambda one: one.label.casefold())
    ]
    return contracts.record(
        id="pantry",
        title="Pantry",
        kind="Pantry",
        href="/recipes/pantry",
        properties={"foods": len(rows)},
        body=write.sections(
            "What each food in your pantry has per 100 g.",
            write.table(["Food", "kcal", "Protein", "Carbs", "Fat", "Source"], rows)
            or "The pantry is empty.",
        ),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    found = [
        recipe(await recipes.read(connection, one.id)) for one in await recipes.recipes(connection)
    ]
    found.append(pantry(await foods.catalogue(connection, None, PANTRY_LIMIT)))
    return found
