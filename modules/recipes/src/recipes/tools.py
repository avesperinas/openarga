from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_nutrients
from arga_tenancy import SPACES_GUC, format_spaces
from recipes import foods, recipes, replace, spaces

MODULE = "recipes"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


class FindRecipes(BaseModel):
    include_archived: bool = Field(
        default=False, description="También las archivadas, que no salen en el recetario."
    )
    query: str | None = Field(
        default=None,
        max_length=60,
        description="Parte del nombre de la receta, p. ej. `porru`. Sin ella, todas.",
    )
    tag: str | None = Field(
        default=None, max_length=40, description="Solo las que llevan esta etiqueta."
    )
    ingredient: str | None = Field(
        default=None,
        max_length=60,
        description="Solo las que llevan este alimento, por su alias, su nombre o parte de ellos.",
    )
    max_minutes: int | None = Field(
        default=None,
        ge=1,
        le=2880,
        description=(
            "Solo las que se hacen en este tiempo o menos, de principio a fin. Una receta sin "
            "pasos no tiene tiempo y no entra en este filtro."
        ),
    )
    max_active_minutes: int | None = Field(
        default=None,
        ge=1,
        le=2880,
        description=(
            "Solo las que te tienen delante este tiempo o menos. Es lo que de verdad decide si "
            "algo entra un martes: una receta de dos horas con hora y media de horno son treinta "
            "minutos de trabajo."
        ),
    )
    limit: int = Field(default=50, ge=1, le=200, description="Cuántas devolver, como mucho.")


SEARCH = text(
    """
    select r.id, r.name, r.servings, v.number as version,
           v.total_minutes, v.active_minutes, r.space_id is not null as shared,
           r.archived_at is not null as archived,
           coalesce(
               array_agg(distinct t.name) filter (where t.name is not null), '{}'
           ) as tags
    from recipes.recipes_recipe r
    join recipes.recipes_recipe_version v on v.id = r.current_version_id
    left join recipes.recipes_recipe_tag rt on rt.recipe_id = r.id
    left join recipes.recipes_tag t on t.id = rt.tag_id
    where (cast(:archived as boolean) or r.archived_at is null)
      and (cast(:query as text) is null
           or recipes.fold(r.name) like '%' || """
    + foods.literal("query")
    + """ || '%')
      and (cast(:max_minutes as int) is null
           or (v.total_minutes is not null and v.total_minutes <= cast(:max_minutes as int)))
      and (cast(:max_active as int) is null
           or (v.active_minutes is not null and v.active_minutes <= cast(:max_active as int)))
      and (cast(:tag as text) is null or exists (
            select 1 from recipes.recipes_recipe_tag rt2
            join recipes.recipes_tag t2 on t2.id = rt2.tag_id
            where rt2.recipe_id = r.id
              and lower(btrim(t2.name)) = lower(btrim(cast(:tag as text)))
      ))
      and (cast(:ingredient as text) is null or exists (
            select 1 from recipes.recipes_recipe_ingredient i
            left join recipes.recipes_food f on f.id = i.food_id
            where i.version_id = v.id
              and (recipes.fold(coalesce(f.name, i.unresolved_name))
                       like '%' || """
    + foods.literal("ingredient")
    + """ || '%'
                   or recipes.fold(f.alias)
                       like '%' || """
    + foods.literal("ingredient")
    + """ || '%')
      ))
    group by r.id, r.name, r.servings, v.number, v.total_minutes, v.active_minutes, r.space_id
    order by """
    + foods.rank("r.name")
    + """, lower(r.name)
    limit :limit
"""
)

COUNT = text("""
    select count(*) as total
    from recipes.recipes_recipe r
    join recipes.recipes_recipe_version v on v.id = r.current_version_id
    where r.archived_at is null
""")


async def find_recipes(connection: AsyncConnection, arguments: FindRecipes) -> dict[str, Any]:
    rows = (
        await connection.execute(
            SEARCH,
            {
                "query": arguments.query,
                "tag": arguments.tag,
                "ingredient": arguments.ingredient,
                "max_minutes": arguments.max_minutes,
                "max_active": arguments.max_active_minutes,
                "limit": arguments.limit,
                "archived": arguments.include_archived,
            },
        )
    ).all()
    counted = (await connection.execute(COUNT)).one()
    return {
        "recipes_in_book": counted.total,
        "returned": len(rows),
        "recipes": [
            {
                "recipe_id": str(row.id),
                "archived": bool(row.archived),
                "name": row.name,
                "servings": row.servings,
                "version": row.version,
                "tags": sorted(row.tags),
                "total_minutes": row.total_minutes,
                "active_minutes": row.active_minutes,
                "shared": row.shared,
            }
            for row in rows
        ],
    }


class GetRecipe(BaseModel):
    recipe_id: str = Field(
        min_length=36, max_length=36, description="La receta, tal cual la da `find_recipes`."
    )
    servings: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description=(
            "Para cuánta gente la quieres. Escala las cantidades y las macros; lo guardado no "
            "cambia. Sin esto, las raciones con las que está escrita."
        ),
    )


async def get_recipe(connection: AsyncConnection, arguments: GetRecipe) -> dict[str, Any]:
    try:
        recipe = await recipes.read(connection, arguments.recipe_id, arguments.servings)
    except recipes.NotFound:
        return {"recipe": None, "note": "esa receta no está en tu recetario"}
    return {"recipe": recipe.model_dump()}


class FindFoods(BaseModel):
    query: str | None = Field(
        default=None, max_length=60, description="Parte del alias o del nombre del alimento."
    )
    limit: int = Field(default=100, ge=1, le=500, description="Cuántos, como mucho.")


async def find_foods(connection: AsyncConnection, arguments: FindFoods) -> dict[str, Any]:
    found = await foods.catalogue(connection, arguments.query, arguments.limit)
    return {
        "total": len(found),
        "foods": [
            {
                "food_id": food.id,
                "alias": food.alias,
                "name": food.name,
                "category": food.category_id,
                "source": food.source,
                "per_100g": food.macros.model_dump(),
                "per": food.per_label,
                "grams_per_unit": food.grams_per_unit,
                "density_g_ml": food.density_g_ml,
                "portions": [one.model_dump() for one in food.portions],
                "edible_fraction": food.edible_fraction,
                "provenance": food.provenance,
                "nutrients_known": len(food.nutrients),
                "micros_from": food.micros_from,
            }
            for food in found
        ],
    }


class ListNutrients(BaseModel):
    pass


async def list_nutrients(connection: AsyncConnection, arguments: ListNutrients) -> dict[str, Any]:
    return {"nutrients": arga_nutrients.catalogue()}


class ListCategories(BaseModel):
    pass


async def list_categories(connection: AsyncConnection, arguments: ListCategories) -> dict[str, Any]:
    found = await recipes.categories(connection)
    return {
        "categories": [
            {"category_id": one.id, "name": one.name, "emoji": one.emoji} for one in found
        ]
    }


class ListTags(BaseModel):
    pass


async def list_tags(connection: AsyncConnection, arguments: ListTags) -> dict[str, Any]:
    found = await recipes.tags(connection)
    return {"tags": [{"name": one.name, "emoji": one.emoji} for one in found]}


class CreateRecipe(recipes.RecipeIn):
    pass


class UpdateRecipe(recipes.RecipeIn):
    recipe_id: str = Field(
        min_length=36,
        max_length=36,
        description="La receta a cambiar, tal cual la da `find_recipes`.",
    )


def _saved(recipe: recipes.Recipe) -> dict[str, Any]:
    unresolved = [
        ingredient.name
        for group in recipe.groups
        for ingredient in group.ingredients
        if ingredient.food_id is None
    ]
    return {
        "recipe_id": recipe.id,
        "name": recipe.name,
        "version": recipe.version,
        "servings": recipe.servings,
        "total_minutes": recipe.kitchen.total_minutes,
        "active_minutes": recipe.kitchen.active_minutes,
        "per_serving": recipe.nutrition.per_serving.model_dump(),
        "unresolved_ingredients": unresolved,
        "macros_note": recipe.nutrition.uncertainty,
    }


async def create_recipe(connection: AsyncConnection, arguments: CreateRecipe) -> dict[str, Any]:
    try:
        recipe_id = await recipes.create(connection, arguments, source="tool")
    except recipes.NotFound as error:
        return {"saved": None, "note": f"no existe: {error}"}
    return {"saved": _saved(await recipes.read(connection, recipe_id))}


async def update_recipe(connection: AsyncConnection, arguments: UpdateRecipe) -> dict[str, Any]:
    body = recipes.RecipeIn(**arguments.model_dump(exclude={"recipe_id"}))
    try:
        await recipes.update(connection, arguments.recipe_id, body, source="tool")
    except recipes.NotFound as error:
        return {"saved": None, "note": f"no existe: {error}"}
    return {"saved": _saved(await recipes.read(connection, arguments.recipe_id))}


class SearchFoodSources(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=60,
        description=(
            "Qué alimento buscar, en la forma en la que lo llamaría su ficha: `leek` o `puerro`, "
            "no `puerros picados`. USDA está en inglés y OpenFoodFacts entiende las dos lenguas. "
            "Un número de 8 a 14 dígitos se busca como código de barras."
        ),
    )


def _candidate(one: foods.CandidateOut) -> dict[str, Any]:
    return {
        "source": one.source,
        "source_ref": one.source_ref,
        "name": one.name,
        "brand": one.brand,
        "macros": one.macros.model_dump(),
        "category_hint": one.category_hint,
        "known_id": one.known_id,
    }


async def search_food_sources(
    connection: AsyncConnection, arguments: SearchFoodSources, client: httpx.AsyncClient
) -> dict[str, Any]:
    found = await foods.search(connection, arguments.query, client)
    return {
        "returned": len(found.candidates),
        "candidates": [_candidate(one) for one in found.candidates],
        "failed": found.failed,
        "discarded": found.discarded,
    }


def _food(food: foods.Food) -> dict[str, Any]:
    return {
        "food_id": food.id,
        "alias": food.alias,
        "name": food.name,
        "category": food.category_id,
        "source": food.source,
        "per_100g": food.macros.model_dump(),
        "per": food.per_label,
        "grams_per_unit": food.grams_per_unit,
        "density_g_ml": food.density_g_ml,
        "corrected": food.corrected,
        "provenance": food.provenance,
        "portions": [one.model_dump() for one in food.portions],
        "edible_fraction": food.edible_fraction,
        "nutrients": food.nutrients,
        "micros_from": food.micros_from,
        "borrowed": food.borrowed,
    }


class ImportFood(foods.ImportIn):
    pass


async def import_food(connection: AsyncConnection, arguments: ImportFood) -> dict[str, Any]:
    try:
        saved = await foods.import_food(connection, arguments)
    except recipes.NotFound as error:
        return {"food": None, "note": f"no existe: {error}; mira `list_categories`"}
    except recipes.Conflict as error:
        return {"food": None, "note": str(error)}
    return {"food": _food(saved)}


class AddManualFood(foods.ManualIn):
    pass


async def add_manual_food(connection: AsyncConnection, arguments: AddManualFood) -> dict[str, Any]:
    try:
        saved = await foods.create_manual(connection, arguments)
    except recipes.NotFound as error:
        return {"food": None, "note": f"no existe: {error}; mira `list_categories`"}
    except recipes.Conflict as error:
        return {"food": None, "note": str(error)}
    return {"food": _food(saved)}


class CorrectFood(foods.CorrectionIn):
    food_id: str = Field(
        min_length=36, max_length=36, description="El alimento, tal cual lo da `find_foods`."
    )


async def correct_food(connection: AsyncConnection, arguments: CorrectFood) -> dict[str, Any]:
    sent = arguments.model_dump(exclude={"food_id"}, exclude_unset=True)
    body = foods.CorrectionIn.model_validate(sent)
    try:
        saved = await foods.correct(connection, arguments.food_id, body)
    except recipes.NotFound as error:
        return {"food": None, "note": f"no existe: {error}"}
    except recipes.Conflict as error:
        return {"food": None, "note": str(error)}
    return {"food": _food(saved)}


class ReplaceFood(BaseModel):
    old_food_id: str = Field(
        min_length=36, max_length=36, description="El que sobra, tal cual lo da `find_foods`."
    )
    new_food_id: str = Field(
        min_length=36, max_length=36, description="El que se queda, tal cual lo da `find_foods`."
    )


async def replace_food(
    connection: AsyncConnection, arguments: ReplaceFood, client: httpx.AsyncClient
) -> dict[str, Any]:
    try:
        done = await replace.replace(
            connection, client, arguments.old_food_id, arguments.new_food_id
        )
    except recipes.NotFound as error:
        return {"replaced": None, "note": f"no existe: {error}"}
    except recipes.Conflict as error:
        return {"replaced": None, "note": str(error)}
    return {"replaced": done}


class SetFoodAlias(foods.AliasIn):
    food_id: str = Field(
        min_length=36, max_length=36, description="El alimento, tal cual lo da `find_foods`."
    )


async def set_food_alias(connection: AsyncConnection, arguments: SetFoodAlias) -> dict[str, Any]:
    body = foods.AliasIn(alias=arguments.alias)
    try:
        saved = await foods.set_alias(connection, arguments.food_id, body)
    except recipes.NotFound as error:
        return {"food": None, "note": f"no existe: {error}"}
    except recipes.Conflict as error:
        return {"food": None, "note": str(error)}
    return {"food": _food(saved)}


class DeleteRecipe(BaseModel):
    recipe_id: str = Field(
        min_length=36, max_length=36, description="La receta, tal cual la da `find_recipes`."
    )
    name: str = Field(
        min_length=1,
        max_length=120,
        description=(
            "El nombre de esa receta, tal como está guardado. Tiene que coincidir o no se borra "
            "nada: es lo que separa un id equivocado de una receta perdida."
        ),
    )


class ArchiveRecipe(BaseModel):
    recipe_id: str = Field(
        min_length=36, max_length=36, description="La receta, tal cual la da `find_recipes`."
    )


async def archive_recipe(connection: AsyncConnection, arguments: ArchiveRecipe) -> dict[str, Any]:
    try:
        await recipes.archive(connection, arguments.recipe_id, True)
    except recipes.NotFound:
        return {"archived": None, "note": "esa receta no está en tu recetario"}
    except recipes.Conflict as error:
        return {"archived": None, "note": str(error)}
    return {"archived": arguments.recipe_id}


async def unarchive_recipe(connection: AsyncConnection, arguments: ArchiveRecipe) -> dict[str, Any]:
    try:
        await recipes.archive(connection, arguments.recipe_id, False)
    except recipes.NotFound:
        return {"unarchived": None, "note": "esa receta no está en tu recetario"}
    except recipes.Conflict as error:
        return {"unarchived": None, "note": str(error)}
    return {"unarchived": arguments.recipe_id}


async def delete_recipe(connection: AsyncConnection, arguments: DeleteRecipe) -> dict[str, Any]:
    try:
        recipe = await recipes.read(connection, arguments.recipe_id)
    except recipes.NotFound:
        return {"deleted": None, "note": "esa receta no está en tu recetario"}
    if recipe.name.strip().casefold() != arguments.name.strip().casefold():
        return {
            "deleted": None,
            "note": (
                f"esa receta se llama «{recipe.name}», no «{arguments.name}»; no he borrado nada"
            ),
        }
    try:
        await recipes.remove(connection, arguments.recipe_id)
    except recipes.Conflict as error:
        return {"deleted": None, "note": str(error)}
    return {"deleted": {"recipe_id": recipe.id, "name": recipe.name, "versions": recipe.versions}}


class ShareRecipe(BaseModel):
    recipe_id: str = Field(
        min_length=36, max_length=36, description="La receta, tal cual la da `find_recipes`."
    )
    space: str | None = Field(
        min_length=1,
        max_length=80,
        description="El nombre del espacio con el que compartirla, o null para que vuelva a ser "
        "solo tuya.",
    )


async def _fresh_spaces(connection: AsyncConnection) -> list[dict]:
    found = await spaces.of_caller()
    ids = tuple(UUID(space["id"]) for space in found)
    await connection.execute(
        text("select set_config(:guc, :spaces, true)"),
        {"guc": SPACES_GUC, "spaces": "{" + format_spaces(ids) + "}"},
    )
    return found


async def share_recipe(connection: AsyncConnection, arguments: ShareRecipe) -> dict[str, Any]:
    space_id = None
    if arguments.space is not None:
        try:
            mine = await _fresh_spaces(connection)
        except spaces.Unavailable as error:
            return {"recipe": None, "note": f"no sé tus espacios: {error}"}
        wanted = arguments.space.strip().casefold()
        match = [one for one in mine if one["name"].strip().casefold() == wanted]
        if not match:
            names = ", ".join(f"«{one['name']}»" for one in mine) or "ninguno"
            return {
                "recipe": None,
                "note": f"no estás en ningún espacio llamado «{arguments.space}»; los tuyos: "
                f"{names}",
            }
        space_id = match[0]["id"]
    try:
        await recipes.share(connection, arguments.recipe_id, space_id)
        recipe = await recipes.read(connection, arguments.recipe_id)
    except recipes.NotFound:
        return {"recipe": None, "note": "esa receta no está en tu recetario"}
    except recipes.Conflict as error:
        return {"recipe": None, "note": str(error)}
    return {
        "recipe": {
            "recipe_id": recipe.id,
            "name": recipe.name,
            "shared": recipe.space_id is not None,
            "mine": recipe.mine,
        }
    }


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]
    spends_quota: bool = False
    asks_kernel: bool = False

    @property
    def asks_the_hub(self) -> bool:
        return self.spends_quota or self.asks_kernel


TOOLS: dict[str, Tool] = {
    "find_recipes": Tool(FindRecipes, find_recipes),
    "get_recipe": Tool(GetRecipe, get_recipe),
    "find_foods": Tool(FindFoods, find_foods),
    "list_categories": Tool(ListCategories, list_categories),
    "list_tags": Tool(ListTags, list_tags),
    "list_nutrients": Tool(ListNutrients, list_nutrients),
    "search_food_sources": Tool(SearchFoodSources, search_food_sources, spends_quota=True),
    "import_food": Tool(ImportFood, import_food),
    "add_manual_food": Tool(AddManualFood, add_manual_food),
    "correct_food": Tool(CorrectFood, correct_food),
    "set_food_alias": Tool(SetFoodAlias, set_food_alias),
    "replace_food": Tool(ReplaceFood, replace_food, asks_kernel=True),
    "create_recipe": Tool(CreateRecipe, create_recipe),
    "update_recipe": Tool(UpdateRecipe, update_recipe),
    "delete_recipe": Tool(DeleteRecipe, delete_recipe),
    "archive_recipe": Tool(ArchiveRecipe, archive_recipe),
    "unarchive_recipe": Tool(ArchiveRecipe, unarchive_recipe),
    "share_recipe": Tool(ShareRecipe, share_recipe),
}
