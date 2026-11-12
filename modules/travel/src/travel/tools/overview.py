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
        description="Lo que se quiere además del viaje: itinerary (los días con sus bloques y lo "
        "guardado sin día), bookings (alojamientos, trayectos y bloques con su reserva), balance "
        "(quién debe a quién), notes (las notas, en trip_notes), checklist (la maleta y lo que "
        "hay que hacer) y documents (los billetes y papeles guardados, sin su contenido). Sin "
        "nada, solo el viaje con sus lugares, trayectos, gastos y el diario.",
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
        description="places: los países o regiones donde se ha estado, con noches y fechas, y los "
        "otros lugares (los que no tienen viaje). summary: las cifras de lo vivido, agrupadas por "
        "año, país o modo de transporte.",
    )
    level: Literal["country", "region"] = Field(default="country", description="Con places.")
    group_by: Literal["year", "country", "mode"] = Field(default="year", description="Con summary.")
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
