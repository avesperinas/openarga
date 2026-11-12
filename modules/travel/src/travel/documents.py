from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel import travel

LIMIT = 20 * 1024 * 1024
LinkKind = Literal["stay", "leg", "block"]
COLUMN: dict[str, str] = {"stay": "stay_id", "leg": "leg_id", "block": "block_id"}


class Link(BaseModel):
    type: LinkKind
    id: str
    title: str


class Document(BaseModel):
    id: str
    name: str
    content_type: str
    size: int
    created_at: datetime
    mine: bool
    link: Link | None


DOCUMENTS = f"""
    select d.id::text as id, d.name, d.content_type, d.size, d.created_at, d.user_id = {ME} as mine,
           d.stay_id::text as stay_id, d.leg_id::text as leg_id, d.block_id::text as block_id,
           coalesce(s.accommodation, sp.name, 'Alojamiento') as stay_title,
           concat_ws(' → ', fp.name, tp.name) as leg_title,
           b.title as block_title
    from travel.travel_document d
    left join travel.travel_stay s on s.id = d.stay_id
    left join travel.travel_place sp on sp.id = s.place_id
    left join travel.travel_leg l on l.id = d.leg_id
    left join travel.travel_place fp on fp.id = l.from_place_id
    left join travel.travel_place tp on tp.id = l.to_place_id
    left join travel.travel_block b on b.id = d.block_id
"""


def _document(row) -> Document:
    link = None
    if row.stay_id:
        link = Link(type="stay", id=row.stay_id, title=row.stay_title)
    elif row.leg_id:
        link = Link(type="leg", id=row.leg_id, title=row.leg_title or "Trayecto")
    elif row.block_id:
        link = Link(type="block", id=row.block_id, title=row.block_title or "Plan")
    return Document(
        id=row.id,
        name=row.name,
        content_type=row.content_type,
        size=row.size,
        created_at=row.created_at,
        mine=bool(row.mine),
        link=link,
    )


async def documents(connection: AsyncConnection, trip_id: str) -> list[Document]:
    rows = await connection.execute(
        text(DOCUMENTS + " where d.trip_id = :trip order by d.created_at"), {"trip": trip_id}
    )
    return [_document(row) for row in rows]


def clean_name(name: str) -> str:
    kept = "".join(ch for ch in name if ch.isprintable() and ch not in '"\\/')
    return kept.strip()[:200] or "documento"


async def _check_link(
    connection: AsyncConnection, trip_id: str, kind: LinkKind | None, link_id: str | None
) -> None:
    if kind is None and link_id is None:
        return
    if kind is None or link_id is None:
        raise travel.Conflict("un enlace lleva su tipo y su id", "INVALID")
    table = {"stay": "travel_stay", "leg": "travel_leg", "block": "travel_block"}[kind]
    found = await connection.scalar(
        text(f"select 1 from travel.{table} where id = cast(:id as uuid) and trip_id = :trip"),
        {"id": link_id, "trip": trip_id},
    )
    if found is None:
        raise travel.NotFound("esa reserva no es de este viaje")


async def attach(
    connection: AsyncConnection,
    trip_id: str,
    name: str,
    content_type: str,
    content: bytes,
    kind: LinkKind | None = None,
    link_id: str | None = None,
) -> list[Document]:
    if not content:
        raise travel.Conflict("el fichero está vacío", "INVALID")
    if len(content) > LIMIT:
        raise travel.Conflict("el fichero pasa de 20 MB", "TOO_LARGE")
    await travel.trip(connection, trip_id)
    await _check_link(connection, trip_id, kind, link_id)
    columns = {column: None for column in COLUMN.values()}
    if kind is not None:
        columns[COLUMN[kind]] = link_id
    await connection.execute(
        text("""
            insert into travel.travel_document
                (trip_id, name, content_type, size, content, stay_id, leg_id, block_id)
            values (:trip, :name, :type, :size, :content, cast(:stay_id as uuid),
                    cast(:leg_id as uuid), cast(:block_id as uuid))
        """),
        {
            "trip": trip_id,
            "name": clean_name(name),
            "type": (content_type or "application/octet-stream")[:120],
            "size": len(content),
            "content": content,
            **columns,
        },
    )
    await travel._touch(connection, trip_id)
    return await documents(connection, trip_id)


class DocumentChange(BaseModel):
    name: str | None = None
    link_type: LinkKind | None = None
    link_id: str | None = None
    unlink: bool = False


async def change(
    connection: AsyncConnection, trip_id: str, document_id: str, request: DocumentChange
) -> list[Document]:
    if request.name is not None and not request.name.strip():
        raise travel.Conflict("el nombre no puede estar vacío", "INVALID")
    relink = request.unlink or request.link_type is not None
    if request.link_type is not None:
        await _check_link(connection, trip_id, request.link_type, request.link_id)
    columns = {column: None for column in COLUMN.values()}
    if request.link_type is not None:
        columns[COLUMN[request.link_type]] = request.link_id
    updated = await connection.execute(
        text("""
            update travel.travel_document set
                name = coalesce(:name, name),
                stay_id = case when :relink then cast(:stay_id as uuid) else stay_id end,
                leg_id = case when :relink then cast(:leg_id as uuid) else leg_id end,
                block_id = case when :relink then cast(:block_id as uuid) else block_id end
            where id = :id and trip_id = :trip
        """),
        {
            "id": document_id,
            "trip": trip_id,
            "name": clean_name(request.name) if request.name is not None else None,
            "relink": relink,
            **columns,
        },
    )
    if updated.rowcount == 0:
        raise travel.NotFound(f"documento {document_id}")
    await travel._touch(connection, trip_id)
    return await documents(connection, trip_id)


async def content(
    connection: AsyncConnection, trip_id: str, document_id: str
) -> tuple[str, str, bytes]:
    row = (
        await connection.execute(
            text("""
                select name, content_type, content from travel.travel_document
                where id = :id and trip_id = :trip
            """),
            {"id": document_id, "trip": trip_id},
        )
    ).first()
    if row is None:
        raise travel.NotFound(f"documento {document_id}")
    return row.name, row.content_type, bytes(row.content)


async def remove(connection: AsyncConnection, trip_id: str, document_id: str) -> list[Document]:
    deleted = await connection.execute(
        text("delete from travel.travel_document where id = :id and trip_id = :trip"),
        {"id": document_id, "trip": trip_id},
    )
    if deleted.rowcount == 0:
        raise travel.NotFound(f"documento {document_id}")
    await travel._touch(connection, trip_id)
    return await documents(connection, trip_id)
