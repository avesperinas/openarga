from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from recipes import foods, hub, recipes
from recipes.recipes import Conflict

RECIPES_USING = text("""
    select distinct r.id from recipes.recipes_recipe r
    join recipes.recipes_recipe_ingredient i on i.version_id = r.current_version_id
    where i.food_id = cast(:old as uuid)
""")

COPY_PORTIONS = text("""
    insert into recipes.recipes_food_portion (food_id, name, grams)
    select cast(:new as uuid), p.name, p.grams from recipes.recipes_food_portion p
     where p.food_id = cast(:old as uuid)
    on conflict (food_id, lower(btrim(name))) do nothing
""")

LEND_FROM_NEW = text("""
    update recipes.recipes_food set micros_from = cast(:new as uuid)
     where micros_from = cast(:old as uuid) and id <> cast(:new as uuid)
""")

ARCHIVE = text("""
    update recipes.recipes_food
       set archived_at = now(), replaced_by = cast(:new as uuid), alias = null
     where id = cast(:old as uuid)
""")

GIVE_ALIAS = text("""
    update recipes.recipes_food set alias = :alias
     where id = cast(:new as uuid) and alias is null
""")


def as_request(recipe: recipes.Recipe, swap: dict[str, str], note: str) -> recipes.RecipeIn:
    ingredients = sorted(
        (one for group in recipe.groups for one in group.ingredients), key=lambda one: one.position
    )
    return recipes.RecipeIn(
        name=recipe.name,
        servings=recipe.servings,
        ingredients=[
            recipes.IngredientIn(
                food_id=None if one.food_id is None else swap.get(one.food_id, one.food_id),
                name=one.name if one.food_id is None else None,
                quantity=one.quantity,
                unit=one.unit,
                note=one.note,
                optional=one.optional,
                portion=one.portion if one.unit == "unit" else None,
                as_purchased=one.as_purchased,
            )
            for one in ingredients
        ],
        steps=[
            recipes.StepIn(
                action=step.action,  # type: ignore[arg-type]
                text=step.text,
                minutes=step.minutes,
                attended=step.attended,
                equipment=step.equipment,  # type: ignore[arg-type]
                after=list(step.after),
                ingredients=list(step.uses),
            )
            for step in sorted(recipe.kitchen.steps, key=lambda step: step.position)
        ],
        tags=[tag.name for tag in recipe.tags],
        note=note[:300],
    )


async def _recipes(
    connection: AsyncConnection, old: foods.Food, new: foods.Food, source: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows = (await connection.execute(RECIPES_USING, {"old": old.id})).all()
    note = f"«{old.label}» sustituido por «{new.label}»"
    done: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for row in rows:
        recipe = await recipes.read(connection, str(row.id))
        try:
            async with connection.begin_nested():
                version = await recipes.update(
                    connection, recipe.id, as_request(recipe, {old.id: new.id}, note), source
                )
        except (Conflict, DBAPIError) as error:
            reason = str(error) if isinstance(error, Conflict) else "no te deja escribirla"
            skipped.append({"recipe_id": recipe.id, "name": recipe.name, "reason": reason})
            continue
        done.append({"recipe_id": recipe.id, "name": recipe.name, "version": version})
    return done, skipped


async def macros(client: httpx.AsyncClient, old: foods.Food, new: foods.Food) -> dict[str, Any]:
    body = contracts.intake_replace_food(
        old_id=old.id, new_id=new.id, old_label=old.label, new_label=new.label
    )
    try:
        response = await hub.ask(client, contracts.INTAKE_REPLACE_FOOD, body)
    except httpx.HTTPError as error:
        return {"done": False, "note": f"el kernel no contesta ({type(error).__name__})"}
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        return {"done": False, "note": detail or f"Macros contesta {response.status_code}"}
    return {"done": True, **contracts.intake_replaced(**response.json())}


async def replace(
    connection: AsyncConnection,
    client: httpx.AsyncClient | None,
    old_id: str,
    new_id: str,
    source: str = "tool",
) -> dict[str, Any]:
    if old_id == new_id:
        raise Conflict("un alimento no se sustituye por sí mismo")
    old = await foods.read(connection, old_id)
    new = await foods.read(connection, new_id)
    if new.archived:
        raise Conflict(f"«{new.label}» ya está sustituido: usa el que lo sustituye")
    if old.nutrients_per != new.nutrients_per:
        raise Conflict(
            "uno va por 100 g y el otro por unidad: lo apuntado con uno no se puede contar "
            "con el otro"
        )
    if old.archived and old.replaced_by != new.id:
        raise Conflict(f"«{old.label}» ya se sustituyó por otro alimento")

    done: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if not old.archived:
        done, skipped = await _recipes(connection, old, new, source)
        await connection.execute(COPY_PORTIONS, {"old": old.id, "new": new.id})
        await connection.execute(LEND_FROM_NEW, {"old": old.id, "new": new.id})
        await connection.execute(ARCHIVE, {"old": old.id, "new": new.id})
        if old.alias:
            await connection.execute(GIVE_ALIAS, {"new": new.id, "alias": old.alias})
    return {
        "old": {"food_id": old.id, "name": old.label},
        "new": {"food_id": new.id, "name": (await foods.read(connection, new.id)).label},
        "recipes": done,
        "skipped": skipped,
        "macros": await macros(client, old, new) if client is not None else None,
    }
