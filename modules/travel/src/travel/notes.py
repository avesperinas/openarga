from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel import travel

Category = Literal["general", "visa", "culture", "tips", "health", "other"]


class NoteIn(BaseModel):
    id: UUID | None = None
    category: Category = "general"
    title: Annotated[str, Field(min_length=1, max_length=120)]
    body: Annotated[str, Field(max_length=20000)] = ""

    @field_validator("title")
    @classmethod
    def tidy(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("el título no puede estar vacío")
        return cleaned


class Note(BaseModel):
    id: str
    category: Category
    title: str
    body: str
    position: int
    updated_at: datetime
    mine: bool


async def notes(connection: AsyncConnection, trip_id: str) -> list[Note]:
    rows = (
        await connection.execute(
            text(f"""
                select id::text as id, category, title, body, position, updated_at,
                       user_id = {ME} as mine
                from travel.travel_note where trip_id = :trip order by position, created_at
            """),
            {"trip": trip_id},
        )
    ).all()
    return [Note(**row._mapping) for row in rows]


async def add_note(connection: AsyncConnection, trip_id: str, request: NoteIn) -> list[Note]:
    await travel.trip(connection, trip_id)
    if request.id is not None:
        exists = await connection.scalar(
            text("select 1 from travel.travel_note where id = :id"), {"id": request.id}
        )
        if exists:
            return await notes(connection, trip_id)
    await connection.execute(
        text("""
            insert into travel.travel_note (id, trip_id, category, title, body, position)
            values (coalesce(cast(:id as uuid), gen_random_uuid()), :trip, :category, :title, :body,
                    (select coalesce(max(position) + 1, 0) from travel.travel_note
                     where trip_id = :trip))
        """),
        {
            "id": str(request.id) if request.id else None,
            "trip": trip_id,
            "category": request.category,
            "title": request.title,
            "body": request.body,
        },
    )
    await travel._touch(connection, trip_id)
    return await notes(connection, trip_id)


async def update_note(
    connection: AsyncConnection, trip_id: str, note_id: str, request: NoteIn
) -> list[Note]:
    updated = await connection.execute(
        text("""
            update travel.travel_note
            set category = :category, title = :title, body = :body, updated_at = now()
            where id = :id and trip_id = :trip
        """),
        {
            "id": note_id,
            "trip": trip_id,
            "category": request.category,
            "title": request.title,
            "body": request.body,
        },
    )
    if updated.rowcount == 0:
        raise travel.NotFound(f"nota {note_id}")
    await travel._touch(connection, trip_id)
    return await notes(connection, trip_id)


async def remove_note(connection: AsyncConnection, trip_id: str, note_id: str) -> list[Note]:
    deleted = await connection.execute(
        text("delete from travel.travel_note where id = :id and trip_id = :trip"),
        {"id": note_id, "trip": trip_id},
    )
    if deleted.rowcount == 0:
        raise travel.NotFound(f"nota {note_id}")
    await travel._touch(connection, trip_id)
    return await notes(connection, trip_id)


async def trip_of(connection: AsyncConnection, note_id: str) -> str:
    found = await connection.scalar(
        text("select trip_id::text from travel.travel_note where id = :id"), {"id": note_id}
    )
    if found is None:
        raise travel.NotFound(f"nota {note_id}")
    return found
