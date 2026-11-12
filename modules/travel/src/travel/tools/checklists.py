from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    lists,
    money,
)
from travel.tools.common import _mutate
from travel.tools.parts import _payer
from travel.tools.reading import GetTrip, _pick


async def _checklist(
    connection: AsyncConnection, trip_id: str, found: list[lists.Item]
) -> dict[str, Any]:
    names = {
        one.id: "yo" if one.me else one.name for one in await money.travellers(connection, trip_id)
    }
    out: dict[str, Any] = {"packing": [], "todo": []}
    for one in found:
        out[one.list].append(
            {
                "item_id": one.id,
                "text": one.text,
                "checked": one.checked,
                "for": names.get(one.traveller_id) if one.traveller_id else None,
            }
        )
    return out


async def get_checklist(connection: AsyncConnection, arguments: GetTrip) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    found = await lists.items(connection, picked["trip"].id)
    return {"trip_id": picked["trip"].id, **await _checklist(connection, picked["trip"].id, found)}


Texts = list[str]


class AddCheckItems(BaseModel):
    trip_id: str
    items: Texts = Field(
        min_length=1, max_length=100, description="Lo que se añade, una cosa por elemento."
    )
    list: lists.ListKind = Field(
        default="packing", description="packing (la maleta) o todo (lo que hay que hacer)."
    )
    for_traveller: str | None = Field(
        default=None, description="A quién le tocan: el nombre de un viajero o «yo»."
    )


async def add_check_items(connection: AsyncConnection, arguments: AddCheckItems) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        owner = None
        if arguments.for_traveller:
            owner = UUID(await _payer(connection, arguments.trip_id, arguments.for_traveller))
        requests = [
            lists.ItemIn(list=arguments.list, text=one, traveller_id=owner)
            for one in arguments.items
        ]
        found = await lists.add_items(connection, arguments.trip_id, requests)
        return await _checklist(connection, arguments.trip_id, found)

    return await _mutate(connection, run)


class CheckItem(BaseModel):
    item_id: UUID
    checked: bool = Field(default=True, description="false la desmarca.")


async def check_item(connection: AsyncConnection, arguments: CheckItem) -> dict[str, Any]:
    item_id = str(arguments.item_id)

    async def run() -> dict[str, Any]:
        trip_id = await lists.trip_of(connection, item_id)
        change = lists.ItemChange(checked=arguments.checked)
        found = await lists.change_item(connection, trip_id, item_id, change)
        return await _checklist(connection, trip_id, found)

    return await _mutate(connection, run)


class ItemRef(BaseModel):
    item_id: UUID


async def remove_check_item(connection: AsyncConnection, arguments: ItemRef) -> dict[str, Any]:
    item_id = str(arguments.item_id)

    async def run() -> dict[str, Any]:
        trip_id = await lists.trip_of(connection, item_id)
        found = await lists.remove_item(connection, trip_id, item_id)
        return await _checklist(connection, trip_id, found)

    return await _mutate(connection, run)


class CopyChecklist(BaseModel):
    trip_id: str = Field(description="El viaje al que se copia.")
    from_trip_id: str = Field(description="El viaje del que se copia.")
    list: lists.ListKind | None = Field(
        default=None, description="Solo esa lista; sin él, las dos."
    )


async def copy_checklist(connection: AsyncConnection, arguments: CopyChecklist) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        found = await lists.copy_from(
            connection, arguments.trip_id, arguments.from_trip_id, arguments.list
        )
        return await _checklist(connection, arguments.trip_id, found)

    return await _mutate(connection, run)
