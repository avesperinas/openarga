from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import travel

LIMIT = 20000


class JournalIn(BaseModel):
    id: UUID | None = None
    body: Annotated[str, Field(max_length=LIMIT)]


class Entry(BaseModel):
    id: str
    trip_id: str
    day: date
    body: str
    updated_at: datetime


COLUMNS = "id::text as id, trip_id::text as trip_id, day, body, updated_at"


async def entries(connection: AsyncConnection, trip_id: str) -> list[Entry]:
    await travel.trip(connection, trip_id)
    rows = (
        await connection.execute(
            text(f"select {COLUMNS} from travel.travel_journal where trip_id = :trip order by day"),
            {"trip": trip_id},
        )
    ).all()
    return [Entry(**row._mapping) for row in rows]


async def every_entry(connection: AsyncConnection) -> list[Entry]:
    rows = (
        await connection.execute(
            text(f"select {COLUMNS} from travel.travel_journal order by day, trip_id")
        )
    ).all()
    return [Entry(**row._mapping) for row in rows]


async def entry(connection: AsyncConnection, trip_id: str, day: date) -> Entry | None:
    row = (
        await connection.execute(
            text(
                f"select {COLUMNS} from travel.travel_journal where trip_id = :trip and day = :day"
            ),
            {"trip": trip_id, "day": day},
        )
    ).one_or_none()
    return Entry(**row._mapping) if row else None


async def write(
    connection: AsyncConnection, trip_id: str, day: date, request: JournalIn
) -> list[Entry]:
    await travel.trip(connection, trip_id)
    await travel._check_dates(connection, trip_id, day)
    body = request.body.strip()
    if not body:
        await connection.execute(
            text("delete from travel.travel_journal where trip_id = :trip and day = :day"),
            {"trip": trip_id, "day": day},
        )
        return await entries(connection, trip_id)
    await connection.execute(
        text("""
            insert into travel.travel_journal (id, trip_id, day, body)
            values (coalesce(cast(:id as uuid), gen_random_uuid()), :trip, :day, :body)
            on conflict (user_id, trip_id, day)
            do update set body = excluded.body,
                updated_at = case when travel_journal.body = excluded.body
                             then travel_journal.updated_at else now() end
        """),
        {"id": str(request.id) if request.id else None, "trip": trip_id, "day": day, "body": body},
    )
    return await entries(connection, trip_id)


async def append(connection: AsyncConnection, trip_id: str, day: date, more: str) -> list[Entry]:
    found = await entry(connection, trip_id, day)
    body = f"{found.body}\n\n{more.strip()}" if found else more
    if len(body) > LIMIT:
        raise travel.Conflict(f"el diario de un día no pasa de {LIMIT} caracteres", "TOO_LONG")
    return await write(connection, trip_id, day, JournalIn(body=body))
