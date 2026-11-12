from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import journal, notes, today
from travel.tools.common import _given, _mutate, _no_null
from travel.tools.reading import GetTrip, _pick


def _notes(found: list[notes.Note]) -> list[dict[str, Any]]:
    return [
        {"note_id": one.id, "category": one.category, "title": one.title, "body": one.body}
        for one in found
    ]


async def get_trip_notes(connection: AsyncConnection, arguments: GetTrip) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    return {
        "trip_id": picked["trip"].id,
        "notes": _notes(await notes.notes(connection, picked["trip"].id)),
    }


NOTE_CATEGORY = Field(
    default="general",
    description="general, visa (visados y documentos), culture (costumbres), tips (consejos), "
    "health (vacunas, seguro, salud) u other.",
)


class AddTripNote(BaseModel):
    trip_id: str
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=20000, description="En Markdown.")
    category: notes.Category = NOTE_CATEGORY


async def add_trip_note(connection: AsyncConnection, arguments: AddTripNote) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        request = notes.NoteIn(
            title=arguments.title, body=arguments.body, category=arguments.category
        )
        return {"notes": _notes(await notes.add_note(connection, arguments.trip_id, request))}

    return await _mutate(connection, run)


class UpdateTripNote(BaseModel):
    note_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=20000, description="Entera, en Markdown.")
    category: notes.Category | None = None


async def update_trip_note(
    connection: AsyncConnection, arguments: UpdateTripNote
) -> dict[str, Any]:
    note_id = str(arguments.note_id)

    async def run() -> dict[str, Any]:
        _no_null(arguments, "title", "body", "category")
        trip_id = await notes.trip_of(connection, note_id)
        current = next(one for one in await notes.notes(connection, trip_id) if one.id == note_id)
        request = notes.NoteIn(
            **{
                "title": current.title,
                "body": current.body,
                "category": current.category,
                **_given(arguments, "title", "body", "category"),
            }
        )
        return {"notes": _notes(await notes.update_note(connection, trip_id, note_id, request))}

    return await _mutate(connection, run)


class NoteRef(BaseModel):
    note_id: UUID


async def remove_trip_note(connection: AsyncConnection, arguments: NoteRef) -> dict[str, Any]:
    note_id = str(arguments.note_id)

    async def run() -> dict[str, Any]:
        trip_id = await notes.trip_of(connection, note_id)
        return {"notes": _notes(await notes.remove_note(connection, trip_id, note_id))}

    return await _mutate(connection, run)


def _journal(found: list[journal.Entry]) -> list[dict[str, Any]]:
    return [{"day": one.day.isoformat(), "text": one.body} for one in found]


class WriteJournal(BaseModel):
    trip_id: str
    day: date | None = Field(
        default=None,
        description="El día del viaje del que se escribe. Sin darlo, el de hoy del viaje en curso, "
        "en España: de viaje lejos, dilo si allí ya es otro día.",
    )
    text: str = Field(
        min_length=1,
        max_length=journal.LIMIT,
        description="Lo que pasó, en sus palabras: lo que la persona te dicta o te pide poner.",
    )
    mode: Literal["append", "replace"] = Field(
        default="append",
        description="append añade un párrafo a lo que ya hay ese día; replace pone el día entero y "
        "pisa lo que hubiera (solo si te lo pide).",
    )


async def write_journal(connection: AsyncConnection, arguments: WriteJournal) -> dict[str, Any]:

    async def run() -> dict[str, Any]:
        day = arguments.day or (await today.today(connection, None)).day
        if arguments.mode == "replace":
            found = await journal.write(
                connection, arguments.trip_id, day, journal.JournalIn(body=arguments.text)
            )
        else:
            found = await journal.append(connection, arguments.trip_id, day, arguments.text)
        return {"trip_id": arguments.trip_id, "day": day.isoformat(), "journal": _journal(found)}

    return await _mutate(connection, run)
