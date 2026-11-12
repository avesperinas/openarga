from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from recipes import hub, recipes

SHORT = {"g": "g", "ml": "ml", "unit": "ud", "tbsp": "cda", "tsp": "cdta", "pinch": "pizca"}


class ShoppingIn(BaseModel):
    servings: int | None = Field(default=None, ge=1, le=50)
    positions: list[int] = Field(min_length=1, max_length=40)


class Unavailable(Exception):
    pass


def quantity_label(quantity: float, unit: str) -> str:
    number = f"{round(quantity, 2):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{number} {SHORT.get(unit, unit)}"


def entries(recipe: recipes.Recipe, positions: list[int]) -> list[dict[str, Any]]:
    wanted = set(positions)
    out = []
    for group in recipe.groups:
        for one in group.ingredients:
            if one.position in wanted:
                out.append({"name": one.name, "quantity": quantity_label(one.quantity, one.unit)})
    return out


async def add(
    connection: AsyncConnection, client: httpx.AsyncClient, recipe_id: str, request: ShoppingIn
) -> dict[str, Any]:
    return await send(client, await body(connection, recipe_id, request))


async def body(connection: AsyncConnection, recipe_id: str, request: ShoppingIn) -> dict[str, Any]:
    recipe = await recipes.read(connection, recipe_id, request.servings)
    items = entries(recipe, request.positions)
    if not items:
        raise recipes.Conflict("ninguno de esos ingredientes está en la receta")
    return contracts.shopping_add(items=items)


async def send(client: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await hub.ask(client, contracts.SHOPPING_ADD, body)
    except httpx.HTTPError as error:
        raise Unavailable(f"el kernel no contesta ({type(error).__name__})") from error
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise Unavailable(detail or f"la lista contesta {response.status_code}")
    return contracts.shopping_added(**response.json())
