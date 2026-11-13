from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_nutrients
from macros import intake, pantry
from macros.common import NotFound, Unavailable, is_uuid, today

LOOKBACK_DAYS = 90

RECIPE_ITEMS = text("""
    select i.recipe_id, i.recipe_version_id, i.name, e.day
    from macros.macros_item i
    join macros.macros_entry e on e.id = i.entry_id
    where i.kind = 'recipe' and e.day >= :since
""")

ITEMS_OF_RECIPE = text("""
    select i.id, i.entry_id, i.name, i.quantity, i.unit, e.day
    from macros.macros_item i
    join macros.macros_entry e on e.id = i.entry_id
    where i.kind = 'recipe' and i.recipe_id = cast(:recipe as uuid)
      and i.recipe_version_id <> cast(:version as uuid)
""")

RECALCULATE = text("""
    update macros.macros_item
       set recipe_version_id = cast(:version as uuid), grams = :grams,
           basis = cast(:basis as jsonb), nutrients = cast(:nutrients as jsonb)
     where id = cast(:id as uuid)
""")


class Outdated(BaseModel):
    recipe_id: str
    name: str
    items: int
    days: list[date]


async def outdated(connection: AsyncConnection, client: httpx.AsyncClient) -> list[Outdated]:
    since = today() - timedelta(days=LOOKBACK_DAYS)
    rows = (await connection.execute(RECIPE_ITEMS, {"since": since})).all()
    by_recipe: dict[str, list[Any]] = {}
    for row in rows:
        by_recipe.setdefault(str(row.recipe_id), []).append(row)
    found = []
    for recipe_id, items in by_recipe.items():
        try:
            current = await pantry.recipe(client, recipe_id)
        except (NotFound, Unavailable):
            continue
        old = [one for one in items if str(one.recipe_version_id) != current["version_id"]]
        if old:
            found.append(
                Outdated(
                    recipe_id=recipe_id,
                    name=current["name"],
                    items=len(old),
                    days=sorted({one.day for one in old}),
                )
            )
    return sorted(found, key=lambda one: one.name.lower())


async def recalculate(
    connection: AsyncConnection, client: httpx.AsyncClient, recipe_id: str
) -> dict[str, Any]:
    if not is_uuid(recipe_id):
        raise NotFound(f"recipe {recipe_id}")
    current = await pantry.recipe(client, recipe_id)
    basis = arga_nutrients.only_known(current["per_serving"])
    basis["_grams"] = float(current.get("grams_per_serving") or 0)
    rows = (
        await connection.execute(
            ITEMS_OF_RECIPE, {"recipe": recipe_id, "version": current["version_id"]}
        )
    ).all()
    entries: dict[str, set[date]] = {}
    for row in rows:
        servings = (
            float(row.quantity)
            if row.unit == "serving"
            else float(row.quantity) / (basis["_grams"] or 1)
        )
        line = intake.compute(
            intake.Line(
                kind="recipe",
                name=row.name,
                quantity=float(row.quantity),
                unit=row.unit,
                grams=round(basis["_grams"] * servings, 2) if basis["_grams"] else None,
                estimated=False,
                recipe_id=recipe_id,
                recipe_version_id=current["version_id"],
                basis=basis,
                basis_per="serving",
            )
        )
        await connection.execute(
            RECALCULATE,
            {
                "id": str(row.id),
                "version": current["version_id"],
                "grams": line.grams,
                "basis": json.dumps(basis),
                "nutrients": json.dumps(line.nutrients or {}),
            },
        )
        entries.setdefault(str(row.entry_id), set()).add(row.day)
    for entry_id, days in entries.items():
        await intake.changed(connection, entry_id, days)
    return {
        "recipe_id": recipe_id,
        "name": current["name"],
        "items": len(rows),
        "days": sorted({day.isoformat() for days in entries.values() for day in days}),
    }
