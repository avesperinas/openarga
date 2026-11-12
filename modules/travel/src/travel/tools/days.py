from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, time
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    bookings,
    itinerary,
)
from travel.tools.common import (
    BOOKING_NAMES,
    BookingArgs,
    PlaceArgument,
    _booking,
    _given,
    _hhmm,
    _mutate,
    _no_null,
    _place,
    _resolve,
)
from travel.tools.reading import GetTrip, _pick


def _block(block: itinerary.Block) -> dict[str, Any]:
    return {
        "block_id": block.id,
        "kind": block.kind,
        "title": block.title,
        "day": block.day.isoformat() if block.day else None,
        "position": block.position,
        "starts_at": block.starts_at.strftime("%H:%M") if block.starts_at else None,
        "ends_at": block.ends_at.strftime("%H:%M") if block.ends_at else None,
        "place": _place(block.place) if block.place else None,
        "visit_id": block.visit_id,
        "notes": block.notes,
        **_booking(block),
    }


def _itinerary(found: itinerary.Itinerary) -> dict[str, Any]:
    days = []
    for day in found.days:
        items: list[dict[str, Any]] = []
        for item in day.items:
            if item.type == "block" and item.block:
                items.append({"type": "block", **_block(item.block)})
            elif item.type == "leg" and item.leg:
                items.append(
                    {
                        "type": "leg",
                        "leg_id": item.leg.id,
                        "from": item.leg.from_place.name,
                        "to": item.leg.to_place.name,
                        "mode": item.leg.mode,
                        "starts_at": _hhmm(item.leg.departs_at),
                        "ends_at": _hhmm(item.leg.arrives_at)
                        if item.leg.arrives_on in (None, item.leg.travelled_on)
                        else None,
                    }
                )
            elif item.stay:
                items.append(
                    {
                        "type": item.type,
                        "stay_id": item.stay.id,
                        "place": item.stay.place.name,
                        "accommodation": item.stay.accommodation,
                        "starts_at": _hhmm(itinerary.starts(item)),
                    }
                )
        days.append(
            {
                "day": day.day.isoformat(),
                "number": day.number,
                "title": day.title,
                "sleeping": day.sleeping.place.name if day.sleeping else None,
                "items": items,
            }
        )
    return {
        "trip_id": found.trip_id,
        "title": found.title,
        "days": days,
        "unscheduled": [_block(one) for one in found.unscheduled],
    }


async def _plan(
    connection: AsyncConnection, action: Callable[[], Awaitable[itinerary.Itinerary]]
) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        return {"itinerary": _itinerary(await action())}

    return await _mutate(connection, run)


async def get_itinerary(connection: AsyncConnection, arguments: GetTrip) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    return _itinerary(await itinerary.itinerary(connection, picked["trip"].id))


KIND = Field(
    default="activity",
    description="activity (ver algo: con lugar, cuenta como visitado y sale en el mapa), "
    "transport, meal, accommodation, free_time u other.",
)


class AddBlock(BookingArgs):
    trip_id: str
    title: str = Field(min_length=1, max_length=120)
    kind: itinerary.Kind = KIND
    day: date | None = Field(
        default=None, description="Sin día, queda guardado para cuando tenga hueco."
    )
    starts_at: time | None = Field(default=None, description="HH:MM. Con hora, entra en su orden.")
    ends_at: time | None = None
    place: PlaceArgument | None = Field(
        default=None, description="Un candidato de find_place o el place_id de uno guardado."
    )
    notes: str | None = Field(default=None, max_length=2000)


async def add_block(connection: AsyncConnection, arguments: AddBlock) -> dict[str, Any]:
    async def run() -> itinerary.Itinerary:
        place = await _resolve(connection, arguments.place) if arguments.place else None
        request = itinerary.BlockIn(
            **arguments.model_dump(exclude={"trip_id", "place"}, exclude_unset=True),
            place_id=place.id if place else None,
        )
        return await itinerary.add_block(connection, arguments.trip_id, request)

    return await _plan(connection, run)


class BlockRef(BaseModel):
    block_id: UUID


class UpdateBlock(BlockRef, BookingArgs):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    kind: itinerary.Kind | None = None
    day: date | None = Field(default=None, description="null lo deja sin día.")
    starts_at: time | None = Field(default=None, description="null quita la hora.")
    ends_at: time | None = None
    place: PlaceArgument | None = Field(default=None, description="null quita el lugar.")
    notes: str | None = Field(default=None, max_length=2000, description="null las borra.")


async def _current_block(connection: AsyncConnection, block_id: str) -> tuple[str, itinerary.Block]:
    trip_id = await itinerary.trip_of(connection, block_id)
    found = next(one for one in await itinerary.blocks(connection, trip_id) if one.id == block_id)
    return trip_id, found


async def update_block(connection: AsyncConnection, arguments: UpdateBlock) -> dict[str, Any]:
    block_id = str(arguments.block_id)

    async def run() -> itinerary.Itinerary:
        _no_null(arguments, "title", "kind")
        trip_id, current = await _current_block(connection, block_id)
        place_id = current.place.id if current.place else None
        if "place" in arguments.model_fields_set:
            place_id = (await _resolve(connection, arguments.place)).id if arguments.place else None
        request = itinerary.BlockIn(
            **{
                "day": current.day,
                "kind": current.kind,
                "title": current.title,
                "starts_at": current.starts_at,
                "ends_at": current.ends_at,
                "notes": current.notes,
                **_given(
                    arguments,
                    "day",
                    "kind",
                    "title",
                    "starts_at",
                    "ends_at",
                    "notes",
                    *BOOKING_NAMES,
                ),
                "place_id": place_id,
            }
        )
        return await itinerary.update_block(connection, trip_id, block_id, request)

    return await _plan(connection, run)


class MoveBlock(BlockRef):
    day: date | None = Field(description="El día al que va, o null para dejarlo sin día.")
    position: int = Field(
        default=1000, ge=0, description="Su puesto en ese día, desde 0. Sin darlo, el último."
    )


async def move_block(connection: AsyncConnection, arguments: MoveBlock) -> dict[str, Any]:
    block_id = str(arguments.block_id)

    async def run() -> itinerary.Itinerary:
        trip_id = await itinerary.trip_of(connection, block_id)
        return await itinerary.move_block(
            connection, trip_id, block_id, arguments.day, arguments.position
        )

    return await _plan(connection, run)


class UpdateDay(BaseModel):
    trip_id: str
    day: date = Field(description="Un día del viaje.")
    title: str | None = Field(
        default=None,
        max_length=80,
        description="«Llegada y Old Fortress». Vacío o null se lo quita.",
    )


async def update_day(connection: AsyncConnection, arguments: UpdateDay) -> dict[str, Any]:
    async def run() -> itinerary.Itinerary:
        return await itinerary.set_day_title(
            connection, arguments.trip_id, arguments.day, arguments.title
        )

    return await _plan(connection, run)


async def remove_block(connection: AsyncConnection, arguments: BlockRef) -> dict[str, Any]:
    block_id = str(arguments.block_id)

    async def run() -> itinerary.Itinerary:
        trip_id = await itinerary.trip_of(connection, block_id)
        return await itinerary.remove_block(connection, trip_id, block_id)

    return await _plan(connection, run)


async def get_bookings(connection: AsyncConnection, arguments: GetTrip) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    found = await bookings.bookings(connection, picked["trip"].id)
    return {
        "trip_id": picked["trip"].id,
        "pending": sum(1 for one in found if not one.booked),
        "bookings": [
            {
                "type": one.type,
                f"{one.type}_id": one.id,
                "title": one.title,
                "detail": one.detail,
                "day": one.day.isoformat() if one.day else None,
                "until": one.until.isoformat() if one.until else None,
                "at": _hhmm(one.at),
                "booked": one.booked,
                **_booking(one),
                **(
                    {"same_ticket_as": {"leg_id": one.ticket_leg_id, "route": one.ticket_of}}
                    if one.ticket_leg_id
                    else {}
                ),
            }
            for one in found
        ],
    }
