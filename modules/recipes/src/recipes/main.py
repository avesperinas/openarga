from __future__ import annotations

import hmac
import os
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
import arga_nutrients
from arga_module.service import Service
from arga_tenancy import current_spaces, require_person
from recipes import (
    foods,
    hub,
    pantry,
    publisher,
    recipes,
    replace,
    shopping,
    spaces,
    tools,
    widgets,
)
from recipes import panel as home_panel

MODULE_ID = "recipes"

service = Service(
    MODULE_ID,
    "Recipes",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
as_app = service.as_app


@app.middleware("http")
async def quota_needs_write(request: Request, call_next):
    name = request.url.path.removeprefix("/tools/")
    tool = tools.TOOLS.get(name) if request.url.path.startswith("/tools/") else None
    scopes = request.headers.get("x-arga-scopes", "").split()
    if (
        request.method == "POST"
        and tool is not None
        and tool.spends_quota
        and tools.role_for_scopes(set(scopes)) is not None
        and f"{MODULE_ID}:write" not in scopes
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": f"{name} gasta cuota de tu clave de las fuentes y eso pide "
                f"{MODULE_ID}:write"
            },
        )
    return await call_next(request)


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, recipes.NotFound):
        return HTTPException(status_code=404, detail=f"no existe: {error}")
    return HTTPException(status_code=409, detail=str(error))


async def _edit(action, *args):
    try:
        async with as_app() as connection:
            return await action(connection, *args)
    except (recipes.NotFound, recipes.Conflict) as error:
        raise _translate(error) from error
    except DBAPIError as error:
        raise HTTPException(status_code=409, detail=str(error.orig).splitlines()[0]) from error


@app.get("/categories")
async def read_categories() -> list[recipes.Category]:
    return await _edit(recipes.categories)


@app.get("/recipes")
async def list_recipes(archived: bool = False) -> list[recipes.RecipeSummary]:
    return await _edit(recipes.recipes, archived)


@app.post("/recipes/{recipe_id}/archive", status_code=204)
async def archive_recipe(recipe_id: UUID) -> None:
    await _edit(recipes.archive, str(recipe_id), True)


@app.post("/recipes/{recipe_id}/unarchive", status_code=204)
async def unarchive_recipe(recipe_id: UUID) -> None:
    await _edit(recipes.archive, str(recipe_id), False)


@app.post("/recipes", status_code=201)
async def create_recipe(request: recipes.RecipeIn) -> recipes.Recipe:
    async with as_app() as connection:
        try:
            recipe_id = await recipes.create(connection, request)
            return await recipes.read(connection, recipe_id)
        except (recipes.NotFound, recipes.Conflict) as error:
            raise _translate(error) from error
        except DBAPIError as error:
            raise HTTPException(status_code=409, detail=str(error.orig).splitlines()[0]) from error


@app.get("/recipes/{recipe_id}")
async def read_recipe(
    recipe_id: UUID, servings: int | None = Query(default=None, ge=1, le=50)
) -> recipes.Recipe:
    return await _edit(recipes.read, str(recipe_id), servings)


@app.post("/recipes/{recipe_id}/shopping")
async def add_to_shopping_list(recipe_id: UUID, request: shopping.ShoppingIn) -> dict:
    try:
        async with as_app() as connection:
            body = await shopping.body(connection, str(recipe_id), request)
        return await shopping.send(source_client(), body)
    except recipes.NotFound as error:
        raise HTTPException(status_code=404, detail=f"no existe: {error}") from error
    except recipes.Conflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except shopping.Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.put("/recipes/{recipe_id}")
async def update_recipe(recipe_id: UUID, request: recipes.RecipeIn) -> recipes.Recipe:
    async with as_app() as connection:
        try:
            await recipes.update(connection, str(recipe_id), request)
            return await recipes.read(connection, str(recipe_id))
        except (recipes.NotFound, recipes.Conflict) as error:
            raise _translate(error) from error
        except DBAPIError as error:
            raise HTTPException(status_code=409, detail=str(error.orig).splitlines()[0]) from error


class SpaceIn(BaseModel):
    space_id: UUID | None


@app.put("/recipes/{recipe_id}/space")
async def share_recipe(recipe_id: UUID, request: SpaceIn) -> recipes.Recipe:
    require_person()
    try:
        found = await spaces.of_caller()
    except spaces.Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    current_spaces.set(tuple(UUID(space["id"]) for space in found))
    if request.space_id is not None and str(request.space_id) not in {s["id"] for s in found}:
        raise HTTPException(status_code=404, detail="no estás en ese espacio")
    space = str(request.space_id) if request.space_id else None

    async def run(connection: AsyncConnection) -> recipes.Recipe:
        await recipes.share(connection, str(recipe_id), space)
        return await recipes.read(connection, str(recipe_id))

    return await _edit(run)


@app.delete("/recipes/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: UUID) -> None:
    await _edit(recipes.remove, str(recipe_id))


@app.get("/nutrients")
async def read_nutrients() -> list[dict]:
    return [
        {
            "key": one.key,
            "name": one.name,
            "unit": one.unit,
            "group": one.group,
            "front": one.front,
            "digits": one.digits,
        }
        for one in arga_nutrients.NUTRIENTS
    ]


@app.get("/tags")
async def read_tags() -> list[recipes.Tag]:
    return await _edit(recipes.tags)


def source_client() -> httpx.AsyncClient:
    return service.client()


@app.get("/foods")
async def list_foods(
    query: str | None = None, limit: int = Query(default=200, ge=1, le=1000)
) -> list[foods.Food]:
    return await _edit(foods.catalogue, query, limit)


@app.get("/foods/search")
async def search_foods(q: str = Query(min_length=2, max_length=60)) -> foods.SearchOut:
    client = source_client()
    found = await hub.search(client, q)
    return await _edit(lambda connection: foods.search(connection, q, client, found))


@app.post("/foods", status_code=201)
async def import_food(request: foods.ImportIn) -> foods.Food:
    return await _edit(foods.import_food, request)


@app.post("/foods/manual", status_code=201)
async def create_manual_food(request: foods.ManualIn) -> foods.Food:
    return await _edit(foods.create_manual, request)


@app.put("/foods/{food_id}/nutrition")
async def correct_food(food_id: UUID, request: foods.CorrectionIn) -> foods.Food:
    return await _edit(foods.correct, str(food_id), request)


class ReplaceIn(BaseModel):
    new_id: UUID


@app.post("/foods/{food_id}/replace")
async def replace_food(food_id: UUID, request: ReplaceIn) -> dict:

    async def here(connection: AsyncConnection):
        old = await foods.read(connection, str(food_id))
        new = await foods.read(connection, str(request.new_id))
        done = await replace.replace(connection, None, str(food_id), str(request.new_id), "app")
        return done, old, new

    done, old, new = await _edit(here)
    return {**done, "macros": await replace.macros(source_client(), old, new)}


@app.put("/foods/{food_id}/alias")
async def set_food_alias(food_id: UUID, request: foods.AliasIn) -> foods.Food:
    return await _edit(foods.set_alias, str(food_id), request)


SERVICES = {
    contracts.PANTRY_SEARCH: contracts.PantrySearch,
    contracts.PANTRY_IMPORT: contracts.PantryImport,
    contracts.PANTRY_NUTRIENTS: contracts.PantryNutrients,
    contracts.RECIPES_SEARCH: contracts.RecipesSearch,
    contracts.RECIPES_NUTRIENTS: contracts.RecipesNutrientsAsk,
    contracts.RECIPES_CREATE: contracts.RecipesCreate,
}


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Recipes no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Recipes")
    shape = SERVICES.get(capability)
    if shape is None:
        raise HTTPException(status_code=404, detail=f"Recipes no sabe hacer '{capability}'")
    require_person()
    try:
        asked = shape.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if capability == contracts.PANTRY_SEARCH:
        client = source_client()
        query = asked.query.strip()
        mine = await _edit(lambda connection: foods.catalogue(connection, query, asked.limit))
        found = await hub.search(client, query) if pantry.asks_outside(asked, len(mine)) else None
        return await _edit(lambda connection: pantry.search(connection, client, asked, found))
    if capability == contracts.PANTRY_IMPORT:
        client = source_client()
        try:
            return await _edit(
                lambda connection: pantry.import_candidate(connection, client, asked)
            )
        except pantry.Unavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    handler = {
        contracts.RECIPES_CREATE: pantry.create_recipe,
        contracts.PANTRY_NUTRIENTS: pantry.nutrients_of,
        contracts.RECIPES_SEARCH: pantry.search_recipes,
        contracts.RECIPES_NUTRIENTS: pantry.recipe_nutrients,
    }[capability]
    answer = await _edit(handler, asked)
    print(f"despensa   {capability} para {x_arga_module}", flush=True)
    return answer


service.serve_ui()
