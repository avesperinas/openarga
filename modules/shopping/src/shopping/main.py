from __future__ import annotations

import hmac
import os
from pathlib import Path
from uuid import UUID

from fastapi import Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_module.service import Service
from arga_tenancy import require_person
from shopping import lists, publisher, shopping, tools, widgets
from shopping import panel as home_panel

MODULE_ID = "shopping"

service = Service(
    MODULE_ID,
    "Shopping",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    actions={"list": widgets.act},
    errors={shopping.NotFound: 404, shopping.Conflict: 409},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
_edit = service.edit


async def _then_list(action, *args) -> shopping.ShoppingList:

    async def both(connection: AsyncConnection) -> shopping.ShoppingList:
        await action(connection, *args)
        return await shopping.read(connection, space=await lists.chosen(connection))

    return await _edit(both)


async def _read(connection: AsyncConnection) -> shopping.ShoppingList:
    return await shopping.read(connection, space=await lists.chosen(connection))


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Shopping no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Shopping")
    if capability != contracts.SHOPPING_ADD:
        raise HTTPException(status_code=404, detail=f"Shopping no sabe hacer '{capability}'")
    require_person()
    try:
        asked = contracts.ShoppingAdd.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    async def add(connection: AsyncConnection) -> dict:
        space = await lists.chosen(connection)
        entries = [
            shopping.Entry(name=one.name, quantity=one.quantity, note=one.note)
            for one in asked.items
        ]
        added = await shopping.add(connection, entries, source="app", space=space)
        return contracts.shopping_added(
            added=[{"name": one.name, "already_on_list": one.already_on_list} for one in added],
            pending=(await shopping.read(connection, space=space)).pending,
        )

    answer = await _edit(add)
    print(f"lista      {len(asked.items)} cosa(s) pedidas por {x_arga_module}", flush=True)
    return answer


@app.get("/categories")
async def read_categories() -> list[shopping.Category]:
    return await _edit(shopping.categories)


@app.get("/list")
async def read_list() -> shopping.ShoppingList:
    return await _edit(_read)


@app.put("/list/owner")
async def choose_list(request: lists.ListOwner) -> shopping.ShoppingList:
    return await _then_list(lists.choose, request)


class AddIn(BaseModel):
    items: list[shopping.Entry] = Field(min_length=1, max_length=40)


class AddOut(BaseModel):
    added: list[shopping.Added]
    list: shopping.ShoppingList


@app.post("/list/items", status_code=201)
async def add_items(request: AddIn) -> AddOut:

    async def both(connection: AsyncConnection) -> AddOut:
        space = await lists.chosen(connection)
        added = await shopping.add(connection, request.items, space=space)
        return AddOut(added=added, list=await shopping.read(connection, space=space))

    return await _edit(both)


@app.put("/list/items/{item_id}/cart")
async def set_cart(item_id: UUID, request: shopping.CartIn) -> shopping.ShoppingList:
    return await _then_list(shopping.set_cart, str(item_id), request)


@app.put("/list/items/{item_id}")
async def update_item(item_id: UUID, request: shopping.ItemIn) -> shopping.ShoppingList:
    return await _then_list(shopping.update_item, str(item_id), request)


@app.post("/list/items/{item_id}/drop")
async def drop_item(item_id: UUID) -> shopping.ShoppingList:
    return await _then_list(shopping.drop, str(item_id))


class FinishOut(BaseModel):
    trip: shopping.Trip
    list: shopping.ShoppingList


class FinishIn(BaseModel):
    id: UUID | None = None


@app.post("/list/finish", status_code=201)
async def finish(request: FinishIn | None = None) -> FinishOut:

    async def both(connection: AsyncConnection) -> FinishOut:
        space = await lists.chosen(connection)
        trip_id = request.id if request else None
        trip = await shopping.finish(connection, space=space, trip_id=trip_id)
        return FinishOut(trip=trip, list=await shopping.read(connection, space=space))

    return await _edit(both)


@app.get("/products")
async def list_products(
    query: str | None = Query(default=None, max_length=60),
) -> list[shopping.Product]:

    async def found(connection: AsyncConnection) -> list[shopping.Product]:
        return await shopping.products(connection, query, space=await lists.chosen(connection))

    return await _edit(found)


@app.put("/products/{product_id}/category")
async def set_category(product_id: UUID, request: shopping.CategoryIn) -> shopping.ShoppingList:
    return await _then_list(shopping.set_category, str(product_id), request)


@app.get("/trips")
async def list_trips(limit: int = Query(default=20, ge=1, le=100)) -> list[shopping.Trip]:

    async def found(connection: AsyncConnection) -> list[shopping.Trip]:
        return await shopping.trips(connection, limit, space=await lists.chosen(connection))

    return await _edit(found)


service.serve_ui()
