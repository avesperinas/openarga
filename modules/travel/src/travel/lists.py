from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import travel

ListKind = Literal["packing", "todo"]


class ItemIn(BaseModel):
    id: UUID | None = None
    list: ListKind = "packing"
    text: Annotated[str, Field(min_length=1, max_length=200)]
    traveller_id: UUID | None = None

    @field_validator("text")
    @classmethod
    def tidy(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("una cosa de la lista no puede estar vacía")
        return cleaned


class ItemChange(BaseModel):
    text: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    checked: bool | None = None
    traveller_id: UUID | None = None


class Item(BaseModel):
    id: str
    list: ListKind
    text: str
    position: int
    checked: bool
    checked_at: datetime | None
    traveller_id: str | None = None


async def items(connection: AsyncConnection, trip_id: str) -> list[Item]:
    rows = (
        await connection.execute(
            text("""
                select id::text as id, list, text, position, checked_at is not null as checked,
                       checked_at, traveller_id::text as traveller_id
                from travel.travel_check_item where trip_id = :trip
                order by list, position, created_at
            """),
            {"trip": trip_id},
        )
    ).all()
    return [Item(**row._mapping) for row in rows]


async def _traveller(connection: AsyncConnection, trip_id: str, traveller_id: UUID | None) -> None:
    if traveller_id is None:
        return
    found = await connection.scalar(
        text("select 1 from travel.travel_traveller where id = :id and trip_id = :trip"),
        {"id": str(traveller_id), "trip": trip_id},
    )
    if found is None:
        raise travel.NotFound("ese viajero no es de este viaje")


async def _insert(connection: AsyncConnection, trip_id: str, request: ItemIn) -> None:
    await _traveller(connection, trip_id, request.traveller_id)
    await connection.execute(
        text("""
            insert into travel.travel_check_item (id, trip_id, list, text, position, traveller_id)
            values (coalesce(cast(:id as uuid), gen_random_uuid()), :trip, :list, :text,
                    (select coalesce(max(position) + 1, 0) from travel.travel_check_item
                     where trip_id = :trip and list = :list),
                    cast(:traveller as uuid))
            on conflict (id) do nothing
        """),
        {
            "id": str(request.id) if request.id else None,
            "trip": trip_id,
            "list": request.list,
            "text": request.text,
            "traveller": str(request.traveller_id) if request.traveller_id else None,
        },
    )


async def add_items(
    connection: AsyncConnection, trip_id: str, requests: list[ItemIn]
) -> list[Item]:
    await travel.trip(connection, trip_id)
    for request in requests:
        await _insert(connection, trip_id, request)
    await travel._touch(connection, trip_id)
    return await items(connection, trip_id)


async def change_item(
    connection: AsyncConnection, trip_id: str, item_id: str, change: ItemChange
) -> list[Item]:
    assign = "traveller_id" in change.model_fields_set
    if assign:
        await _traveller(connection, trip_id, change.traveller_id)
    updated = await connection.execute(
        text("""
            update travel.travel_check_item
            set text = coalesce(:text, text),
                traveller_id = case when :assign then cast(:traveller as uuid)
                                    else traveller_id end,
                checked_at = case
                    when cast(:checked as boolean) is null then checked_at
                    when cast(:checked as boolean) then coalesce(checked_at, now())
                    else null
                end
            where id = :id and trip_id = :trip
        """),
        {
            "id": item_id,
            "trip": trip_id,
            "text": change.text,
            "checked": change.checked,
            "assign": assign,
            "traveller": str(change.traveller_id) if change.traveller_id else None,
        },
    )
    if updated.rowcount == 0:
        raise travel.NotFound(f"cosa de la lista {item_id}")
    await travel._touch(connection, trip_id)
    return await items(connection, trip_id)


async def remove_item(connection: AsyncConnection, trip_id: str, item_id: str) -> list[Item]:
    deleted = await connection.execute(
        text("delete from travel.travel_check_item where id = :id and trip_id = :trip"),
        {"id": item_id, "trip": trip_id},
    )
    if deleted.rowcount == 0:
        raise travel.NotFound(f"cosa de la lista {item_id}")
    await travel._touch(connection, trip_id)
    return await items(connection, trip_id)


async def copy_from(
    connection: AsyncConnection, trip_id: str, source_id: str, kind: ListKind | None = None
) -> list[Item]:
    if source_id == trip_id:
        raise travel.Conflict("un viaje no copia sus propias listas", "INVALID")
    await travel.trip(connection, trip_id)
    source = await items(connection, source_id)
    if (
        not source
        and await connection.scalar(
            text("select 1 from travel.travel_trip where id = :id"), {"id": source_id}
        )
        is None
    ):
        raise travel.NotFound(f"viaje {source_id}")
    have = {(one.list, one.text.lower()) for one in await items(connection, trip_id)}
    for one in source:
        if kind is not None and one.list != kind:
            continue
        if (one.list, one.text.lower()) in have:
            continue
        have.add((one.list, one.text.lower()))
        await _insert(connection, trip_id, ItemIn(list=one.list, text=one.text))
    await travel._touch(connection, trip_id)
    return await items(connection, trip_id)


async def trip_of(connection: AsyncConnection, item_id: str) -> str:
    found = await connection.scalar(
        text("select trip_id::text from travel.travel_check_item where id = :id"), {"id": item_id}
    )
    if found is None:
        raise travel.NotFound(f"cosa de la lista {item_id}")
    return found
