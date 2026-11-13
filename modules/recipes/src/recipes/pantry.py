from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
import arga_nutrients
from recipes import foods, hub, recipes, sources


class Unavailable(Exception):
    pass


def _pantry_food(food: foods.Food) -> dict[str, Any]:
    return contracts.pantry_food(
        id=food.id,
        name=food.name,
        label=food.label,
        source=food.source,
        nutrients=food.nutrients,
        grams_per_unit=food.grams_per_unit,
        density_g_ml=food.density_g_ml,
        portions={one.name.strip().lower(): one.grams for one in food.portions},
        edible_fraction=food.edible_fraction,
        nutrients_per=food.nutrients_per,
        unit_name=food.unit_name,
    )


def asks_outside(asked: contracts.PantrySearch, mine: int) -> bool:
    return asked.outside and mine < asked.enough


async def search(
    connection: AsyncConnection,
    client: httpx.AsyncClient,
    asked: contracts.PantrySearch,
    outside: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mine = await foods.catalogue(connection, asked.query.strip(), asked.limit)
    candidates: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    if asks_outside(asked, len(mine)):
        found = await foods.search(connection, asked.query.strip(), client, outside)
        failed = found.failed
        for one in found.candidates:
            if one.known_id:
                continue
            candidates.append(
                {
                    "source": one.source,
                    "source_ref": one.source_ref,
                    "name": one.name,
                    "brand": one.brand,
                    "category_hint": one.category_hint,
                    "nutrients": one.nutrients
                    or {
                        "kcal": one.macros.kcal,
                        "protein": one.macros.protein,
                        "fat": one.macros.fat,
                        "carbs": one.macros.carbs,
                    },
                }
            )
    return contracts.pantry_found(
        foods=[_pantry_food(one) for one in mine],
        candidates=candidates[: asked.limit],
        failed=failed,
    )


async def fetch(client: httpx.AsyncClient, source: str, ref: str) -> sources.Candidate:
    try:
        response = await hub.ask(
            client, "food.get", {"items": [{"source": source, "source_ref": ref}]}
        )
    except httpx.HTTPError as error:
        raise Unavailable(f"the kernel is not answering ({type(error).__name__})") from error
    if response.status_code != 200:
        raise Unavailable(f"the hub answers {response.status_code}")
    answer = response.json()
    for raw in answer.get("candidates") or []:
        candidate = sources.Candidate.from_hub(raw)
        if (candidate.source, candidate.source_ref) == (source, ref):
            return candidate
    for failed in answer.get("failed") or []:
        if failed.get("source") == source:
            raise Unavailable(failed.get("reason") or f"{source} is not answering")
    raise recipes.NotFound(f"{source}:{ref} in its source")


async def import_candidate(
    connection: AsyncConnection, client: httpx.AsyncClient, asked: contracts.PantryImport
) -> dict[str, Any]:
    known = await foods._known(connection, asked.source, asked.source_ref)
    if known:
        if (asked.alias or "").strip():
            return _pantry_food(
                await foods.set_alias(connection, known, foods.AliasIn(alias=asked.alias))
            )
        return _pantry_food(await foods.read(connection, known))
    candidate = await fetch(client, asked.source, asked.source_ref)
    values = arga_nutrients.only_known(candidate.nutrients)
    category = candidate.category_hint
    if (await connection.execute(foods.CATEGORY_EXISTS, {"id": category})).first() is None:
        category = "other"
    food = await foods.import_food(
        connection,
        foods.ImportIn(
            source=candidate.source,
            source_ref=candidate.source_ref,
            name=candidate.name[:120],
            category_id=category,
            macros=foods.MacrosIn(
                kcal=min(candidate.kcal_100g, 1000),
                protein=min(candidate.protein_100g, 100),
                fat=min(candidate.fat_100g, 100),
                carbs=min(candidate.carbs_100g, 100),
                fiber=None if candidate.fiber_100g is None else min(candidate.fiber_100g, 100),
                salt=None if candidate.salt_100g is None else min(candidate.salt_100g, 100),
            ),
            grams_per_unit=asked.grams_per_unit,
            alias=asked.alias,
            nutrients=values,
            portions=_portions(candidate.portions),
        ),
    )
    return _pantry_food(food)


def _portions(raw: list[dict]) -> list[foods.Portion]:
    found: list[foods.Portion] = []
    for one in raw or []:
        try:
            portion = foods.Portion(name=str(one["name"]), grams=float(one["grams"]))
        except (KeyError, TypeError, ValueError):
            continue
        if portion.name.strip().lower() not in {other.name.strip().lower() for other in found}:
            found.append(portion)
    return found


BY_IDS = text(foods.SELECT + " where id = any(cast(:ids as uuid[]))")


async def nutrients_of(
    connection: AsyncConnection, asked: contracts.PantryNutrients
) -> dict[str, Any]:
    valid = [one for one in asked.ids if _is_uuid(one)]
    rows = (await connection.execute(BY_IDS, {"ids": valid})).all()
    return contracts.pantry_foods(foods=[_pantry_food(foods._food(row)) for row in rows])


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


async def search_recipes(
    connection: AsyncConnection, asked: contracts.RecipesSearch
) -> dict[str, Any]:
    scored = [
        (score, index, one)
        for index, one in enumerate(await recipes.recipes(connection))
        if (score := foods.closeness(asked.query, one.name)) is not None
    ]
    found = [one for _, _, one in sorted(scored, key=lambda kept: kept[:2])]
    return contracts.recipes_found(
        recipes=[
            {"id": one.id, "name": one.name, "servings": one.servings}
            for one in found[: asked.limit]
        ]
    )


async def recipe_nutrients(
    connection: AsyncConnection, asked: contracts.RecipesNutrientsAsk
) -> dict[str, Any]:
    if not _is_uuid(asked.id):
        raise recipes.NotFound(f"la receta {asked.id}")
    recipe = await recipes.read(connection, asked.id)
    serving = recipe.nutrition
    return contracts.recipe_nutrients(
        id=recipe.id,
        name=recipe.name,
        version_id=recipe.version_id,
        version=recipe.version,
        servings=recipe.servings,
        per_serving=serving.nutrients,
        grams_per_serving=round(
            sum(one.grams or 0 for g in recipe.groups for one in g.ingredients) / recipe.servings,
            1,
        ),
        missing=[
            one.name
            for g in recipe.groups
            for one in g.ingredients
            if one.grams is None or one.food_id is None
        ],
        coverage=serving.coverage,
    )


BATCH = 25

WITHOUT_NUTRIENTS = text("""
    select id, source, source_ref from recipes.recipes_food
    where source in ('usda', 'off') and source_ref is not null and nutrients is null
      and (nutrients_checked_at is null or nutrients_checked_at < now() - interval '1 day')
    order by imported_at
    limit :batch
""")

FILL = text("""
    update recipes.recipes_food
       set nutrients = cast(:nutrients as jsonb), nutrients_checked_at = now()
     where id = cast(:id as uuid)
""")

CHECKED = text("""
    update recipes.recipes_food set nutrients_checked_at = now()
     where id = cast(:id as uuid)
""")


async def refill(connection: AsyncConnection, client: httpx.AsyncClient) -> int:
    rows = (await connection.execute(WITHOUT_NUTRIENTS, {"batch": BATCH})).all()
    if not rows:
        return 0
    try:
        response = await hub.ask(
            client,
            "food.get",
            {"items": [{"source": row.source, "source_ref": row.source_ref} for row in rows]},
        )
    except httpx.HTTPError as error:
        raise Unavailable(f"the kernel is not answering ({type(error).__name__})") from error
    if response.status_code != 200:
        raise Unavailable(f"the hub answers {response.status_code}")
    answer = response.json()
    failed = {one.get("source") for one in answer.get("failed") or []}
    brought = {}
    for raw in answer.get("candidates") or []:
        candidate = sources.Candidate.from_hub(raw)
        brought[(candidate.source, candidate.source_ref)] = arga_nutrients.only_known(
            candidate.nutrients
        )
    filled = 0
    for row in rows:
        values = brought.get((row.source, row.source_ref))
        if values:
            await connection.execute(FILL, {"id": str(row.id), "nutrients": json.dumps(values)})
            filled += 1
        elif row.source not in failed:
            await connection.execute(CHECKED, {"id": str(row.id)})
    return filled


async def create_recipe(
    connection: AsyncConnection, asked: contracts.RecipesCreate
) -> dict[str, Any]:
    request = recipes.RecipeIn(
        name=asked.name,
        servings=asked.servings,
        ingredients=[
            recipes.IngredientIn(
                food_id=one.food_id, quantity=one.quantity, unit=one.unit, portion=one.portion
            )
            for one in asked.ingredients
        ],
    )
    recipe_id = await recipes.create(connection, request, source="app")
    found = await recipes.read(connection, recipe_id)
    return contracts.RecipeCreated(recipe_id=found.id, version_id=found.version_id).model_dump()
