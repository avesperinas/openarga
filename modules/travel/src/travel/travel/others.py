from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel.travel.common import Conflict, NotFound, Source
from travel.travel.places import Place, place_by_id
from travel.travel.read import _joined_place, _place_select


class OtherPlaceIn(BaseModel):
    place_id: str
    note: Annotated[str | None, Field(max_length=300)] = None


class OtherPlace(BaseModel):
    id: str
    place: Place
    note: str | None
    source: str


async def other_places(connection: AsyncConnection) -> list[OtherPlace]:
    rows = (
        await connection.execute(
            text(f"""
                select o.id::text as other_id, o.note, o.source, {_place_select("p", "p_")}
                from travel.travel_other_place o
                join travel.travel_place p on p.id = o.place_id
                order by p.name
            """)
        )
    ).all()
    return [
        OtherPlace(
            id=row.other_id, place=_joined_place(row, "p_"), note=row.note, source=row.source
        )
        for row in rows
    ]


async def add_other_place(
    connection: AsyncConnection, request: OtherPlaceIn, source: Source = "app"
) -> OtherPlace:
    await place_by_id(connection, request.place_id)
    note = " ".join(request.note.split()) if request.note else None
    other_id = await connection.scalar(
        text("""
            insert into travel.travel_other_place (place_id, note, source)
            values (:place, :note, :source)
            on conflict (user_id, place_id)
                do update set note = coalesce(excluded.note, travel_other_place.note)
            returning id::text
        """),
        {"place": request.place_id, "note": note, "source": source},
    )
    return next(one for one in await other_places(connection) if one.id == other_id)


async def delete_other_place(connection: AsyncConnection, other_id: str) -> None:
    deleted = await connection.execute(
        text("delete from travel.travel_other_place where id = :id"), {"id": other_id}
    )
    if deleted.rowcount == 0:
        raise NotFound(f"lugar sin viaje {other_id}")


async def update_other_place(
    connection: AsyncConnection, other_id: str, request: OtherPlaceIn
) -> OtherPlace:
    await place_by_id(connection, request.place_id)
    clash = await connection.scalar(
        text(
            "select id::text from travel.travel_other_place where place_id = :place and id <> :id"
        ),
        {"place": request.place_id, "id": other_id},
    )
    if clash:
        raise Conflict(
            "ese lugar ya está entre los otros lugares",
            "DUPLICATE_PLACE",
            [{"other_place_id": clash}],
        )
    updated = await connection.execute(
        text("update travel.travel_other_place set place_id = :place, note = :note where id = :id"),
        {
            "id": other_id,
            "place": request.place_id,
            "note": " ".join(request.note.split()) if request.note else None,
        },
    )
    if updated.rowcount == 0:
        raise NotFound(f"lugar sin viaje {other_id}")
    return next(one for one in await other_places(connection) if one.id == other_id)


class HomeIn(BaseModel):
    place_id: str


async def home(connection: AsyncConnection) -> Place | None:
    row = (
        await connection.execute(
            text(f"""
                select {_place_select("p", "p_")}
                from travel.travel_home h
                join travel.travel_place p on p.id = h.place_id
            """)
        )
    ).first()
    return _joined_place(row, "p_") if row else None


async def set_home(connection: AsyncConnection, request: HomeIn) -> Place:
    await place_by_id(connection, request.place_id)
    await connection.execute(
        text("""
            insert into travel.travel_home (place_id) values (:place)
            on conflict (user_id) do update set place_id = excluded.place_id, updated_at = now()
        """),
        {"place": request.place_id},
    )
    found = await home(connection)
    assert found is not None
    return found


async def clear_home(connection: AsyncConnection) -> None:
    await connection.execute(text("delete from travel.travel_home"))
