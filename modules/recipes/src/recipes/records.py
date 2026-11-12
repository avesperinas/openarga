from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from recipes import foods, recipes

APP = "recipes"
PANTRY_LIMIT = 100_000


def _amount(one: recipes.IngredientOut) -> str:
    return f"{write.trimmed(one.quantity)} {one.unit}".strip()


def recipe(found: recipes.Recipe) -> dict[str, Any]:
    kitchen = found.kitchen
    serving = found.nutrition.per_serving
    groups = []
    for group in found.groups:
        lines = "\n".join(
            f"- {one.name}: {_amount(one)}"
            + (f" · {one.note}" if one.note else "")
            + (" (opcional)" if one.optional else "")
            for one in group.ingredients
        )
        groups.append(f"### {group.emoji} {group.name}\n\n{lines}")
    steps = "\n".join(
        f"{step.position + 1}. {step.text}"
        + (f" · {step.minutes} min" if step.minutes else "")
        + ("" if step.attended else " (sin estar delante)")
        for step in sorted(kitchen.steps, key=lambda one: one.position)
    )
    macros = (
        f"{write.number(serving.kcal)} kcal · {write.trimmed(serving.protein, 1)} g proteína · "
        f"{write.trimmed(serving.carbs, 1)} g hidratos · {write.trimmed(serving.fat, 1)} g grasa"
    )
    if found.nutrition.uncertainty:
        macros += f"\n\n*{found.nutrition.uncertainty}*"
    lead = (
        f"Para {found.servings} {'ración' if found.servings == 1 else 'raciones'} · "
        f"{kitchen.total_minutes} min en total, {kitchen.active_minutes} delante · "
        f"versión {found.version}"
    )
    properties: dict[str, Any] = {
        "raciones": found.servings,
        "tiempo_total_min": kitchen.total_minutes,
        "tiempo_activo_min": kitchen.active_minutes,
        "kcal_racion": round(serving.kcal),
        "proteina_racion_g": round(serving.protein, 1),
        "hidratos_racion_g": round(serving.carbs, 1),
        "grasa_racion_g": round(serving.fat, 1),
        "version": found.version,
    }
    if found.tags:
        properties["etiquetas"] = [tag.name for tag in found.tags]
    return contracts.record(
        id=f"recipe:{found.id}",
        title=found.name,
        kind="Receta",
        href=f"/recipes/receta/{found.id}",
        folder="Recetas",
        properties=properties,
        body=write.sections(
            lead + ".",
            found.note,
            "## Ingredientes\n\n" + "\n\n".join(groups) if groups else None,
            f"## Pasos\n\n{steps}" if steps else None,
            f"## Por ración\n\n{macros}",
        ),
    )


def pantry(found: list[foods.Food]) -> dict[str, Any]:
    rows = [
        [
            one.label,
            write.trimmed(one.macros.kcal, 0),
            write.trimmed(one.macros.protein, 1),
            write.trimmed(one.macros.carbs, 1),
            write.trimmed(one.macros.fat, 1),
            one.source,
        ]
        for one in sorted(found, key=lambda one: one.label.casefold())
    ]
    return contracts.record(
        id="pantry",
        title="Despensa",
        kind="Despensa",
        href="/recipes/despensa",
        properties={"alimentos": len(rows)},
        body=write.sections(
            "Lo que lleva cada alimento de tu despensa por 100 g.",
            write.table(["Alimento", "kcal", "Proteína", "Hidratos", "Grasa", "Fuente"], rows)
            or "La despensa está vacía.",
        ),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    found = [
        recipe(await recipes.read(connection, one.id)) for one in await recipes.recipes(connection)
    ]
    found.append(pantry(await foods.catalogue(connection, None, PANTRY_LIMIT)))
    return found
