from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from travel.tools.accounts import get_trip_balance
from travel.tools.checklists import get_checklist
from travel.tools.days import get_bookings, get_itinerary
from travel.tools.papers import get_trip_documents
from travel.tools.reading import (
    GetOtherPlaces,
    GetPlacesVisited,
    GetTrip,
    SummariseTravel,
    _pick,
    get_other_places,
    get_places_visited,
    summarise_travel,
)
from travel.tools.reading import get_trip as trip_detail
from travel.tools.writing import get_trip_notes

Part = Literal["itinerary", "bookings", "balance", "notes", "checklist", "documents"]

PARTS: dict[str, Callable[[AsyncConnection, GetTrip], Awaitable[dict[str, Any]]]] = {
    "itinerary": get_itinerary,
    "bookings": get_bookings,
    "balance": get_trip_balance,
    "notes": get_trip_notes,
    "checklist": get_checklist,
    "documents": get_trip_documents,
}


class GetTripWith(GetTrip):
    include: list[Part] = Field(
        default_factory=list,
        description=(
            "What is wanted besides the trip: itinerary (the days with their blocks and what is "
            "kept without a day), bookings (lodgings, legs and blocks with their booking), balance"
            " (who owes whom), notes (the notes, in trip_notes), checklist (the suitcase and what "
            "has to be done) and documents (the tickets and papers stored, without their content)."
            " With nothing, only the trip with its places, legs, expenses and the journal."
        ),
    )


KEYS = {name: name for name in PARTS} | {"notes": "trip_notes"}


def _part(name: str, found: dict[str, Any]) -> Any:
    rest = {key: value for key, value in found.items() if key != "trip_id"}
    return rest[name] if set(rest) == {name} else rest


async def get_trip(connection: AsyncConnection, arguments: GetTripWith) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    found = await trip_detail(connection, GetTrip(trip_id=picked["trip"].id))
    one = GetTrip(trip_id=picked["trip"].id)
    for name in dict.fromkeys(arguments.include):
        found[KEYS[name]] = _part(name, await PARTS[name](connection, one))
    return found


class GetTravel(BaseModel):
    view: Literal["places", "summary"] = Field(
        default="places",
        description=(
            "places: the countries or regions visited, with nights and dates, and the other places"
            " (those without a trip). summary: the figures of what was lived, grouped by year, "
            "country or mode of transport."
        ),
    )
    level: Literal["country", "region"] = Field(default="country", description="With places.")
    group_by: Literal["year", "country", "mode"] = Field(
        default="year", description="With summary."
    )
    since: date | None = None
    until: date | None = None


async def get_travel(connection: AsyncConnection, arguments: GetTravel) -> dict[str, Any]:
    if arguments.view == "summary":
        return await summarise_travel(
            connection,
            SummariseTravel(
                group_by=arguments.group_by, since=arguments.since, until=arguments.until
            ),
        )
    found = await get_places_visited(
        connection,
        GetPlacesVisited(level=arguments.level, since=arguments.since, until=arguments.until),
    )
    others = await get_other_places(connection, GetOtherPlaces())
    return {**found, "other_places": others["other_places"]}
