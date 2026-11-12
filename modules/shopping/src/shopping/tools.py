from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from shopping import lists, names, shopping

MODULE = "shopping"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"

Section = Literal[
    "produce",
    "bakery",
    "meat",
    "fish",
    "deli",
    "dairy",
    "pantry",
    "breakfast",
    "frozen",
    "drinks",
    "cleaning",
    "hygiene",
    "other",
]


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _item(one: shopping.Item) -> dict[str, Any]:
    return {"item_id": one.id, "name": one.name, "quantity": one.quantity, "note": one.note}


def _habit(one: shopping.Product) -> dict[str, Any]:
    return {
        "product_id": one.id,
        "name": one.name,
        "section": one.category_id,
        "times_bought": one.times,
        "last_bought": one.last.isoformat() if one.last else None,
        "every_days": one.every_days,
        "every": one.every,
        "since": one.since,
        "due": one.due,
        "on_list": one.on_list,
    }


class GetShoppingList(BaseModel):
    pass


async def get_shopping_list(
    connection: AsyncConnection, arguments: GetShoppingList
) -> dict[str, Any]:
    found = await shopping.read(connection, space=await lists.chosen(connection))
    return {
        "shared": found.space_id is not None,
        "pending": found.pending,
        "in_cart": found.in_cart,
        "sections": [
            {
                "section": group.category_id,
                "name": group.name,
                "emoji": group.emoji,
                "items": [_item(one) for one in group.items],
            }
            for group in found.groups
        ],
        "cart": [_item(one) for one in found.cart],
        "due": [_habit(one) for one in found.due],
    }


class GetPurchaseHistory(BaseModel):
    query: str | None = Field(
        default=None,
        max_length=60,
        description="Solo los productos con una palabra que empiece así: `cafe`, `leche`.",
    )
    trips: int = Field(
        default=10, ge=0, le=50, description="Cuántas compras recientes traer, con lo que llevaban."
    )
    limit: int = Field(default=50, ge=1, le=300, description="Cuántos productos, como mucho.")


async def get_purchase_history(
    connection: AsyncConnection, arguments: GetPurchaseHistory
) -> dict[str, Any]:
    space = await lists.chosen(connection)
    everything = await shopping.products(connection, arguments.query, space=space)
    recent = (
        await shopping.trips(connection, arguments.trips, space=space) if arguments.trips else []
    )
    return {
        "products_known": len(everything),
        "products": [_habit(one) for one in everything[: arguments.limit]],
        "recent_trips": [
            {
                "date": trip.finished_at.astimezone(shopping.MADRID).date().isoformat(),
                "items": trip.items,
                "products": [one.name for one in trip.products],
            }
            for trip in recent
        ],
    }


class Entry(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "Cómo se dice en casa y en español, sin cantidad: `leche`, `pechuga de pollo`. Si ya "
            "lo has comprado alguna vez, el mismo nombre lo reconoce."
        ),
    )
    quantity: str | None = Field(
        default=None, max_length=30, description="Corta y como se diría: `2`, `1 kg`, `pack de 6`."
    )
    note: str | None = Field(
        default=None, max_length=120, description="Lo que ayuda a elegirlo: `la sin lactosa`."
    )
    section: Section | None = Field(
        default=None,
        description=(
            "La sección del súper, solo si es un producto nuevo y la sabes: sin ella la pone un "
            "diccionario, y lo que no conoce va a `other`."
        ),
    )


class AddToList(BaseModel):
    items: list[Entry] = Field(min_length=1, max_length=40)


async def add_to_list(connection: AsyncConnection, arguments: AddToList) -> dict[str, Any]:
    entries = [
        shopping.Entry(name=one.name, quantity=one.quantity, note=one.note, category_id=one.section)
        for one in arguments.items
    ]
    space = await lists.chosen(connection)
    try:
        async with connection.begin_nested():
            added = await shopping.add(connection, entries, source="tool", space=space)
    except (shopping.NotFound, shopping.Conflict) as error:
        return {"added": [], "note": f"no he apuntado nada: {error}"}
    return {
        "added": [
            {
                "name": one.name,
                "section": one.category_id,
                "already_on_list": one.already_on_list,
                "new_product": one.new_product,
            }
            for one in added
        ],
        "shared": space is not None,
        "pending": (await shopping.read(connection, space=space)).pending,
    }


class RemoveFromList(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=80,
        description="El producto tal como está en la lista, o el principio de una de sus palabras.",
    )


async def remove_from_list(
    connection: AsyncConnection, arguments: RemoveFromList
) -> dict[str, Any]:
    found = await shopping.read(connection, space=await lists.chosen(connection))
    open_items = [one for group in found.groups for one in group.items] + found.cart
    wanted = names.key(arguments.name)
    exact = [one for one in open_items if names.key(one.name) == wanted]
    matches = exact or [one for one in open_items if names.starts_a_word(arguments.name, one.name)]
    if len(matches) != 1:
        return {
            "removed": None,
            "note": (
                f"«{arguments.name}» no está en la lista"
                if not matches
                else f"«{arguments.name}» puede ser varios; di cuál"
            ),
            "candidates": [one.name for one in (matches or open_items)][:20],
        }
    await shopping.drop(connection, matches[0].id)
    return {
        "removed": {"name": matches[0].name},
        "pending": found.pending - (not matches[0].in_cart),
    }


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    "get_shopping_list": Tool(GetShoppingList, get_shopping_list),
    "get_purchase_history": Tool(GetPurchaseHistory, get_purchase_history),
    "add_to_list": Tool(AddToList, add_to_list),
    "remove_from_list": Tool(RemoveFromList, remove_from_list),
}
