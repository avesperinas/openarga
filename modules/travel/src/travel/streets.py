from __future__ import annotations

import base64
from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import hub, itinerary

Profile = Literal["foot", "bike", "car"]


class Unavailable(Exception):
    pass


async def tile(connection: AsyncConnection, z: int, x: int, y: int) -> bytes | None:
    found = (
        await connection.execute(
            text("select data from travel.travel_tile where z = :z and x = :x and y = :y"),
            {"z": z, "x": x, "y": y},
        )
    ).one_or_none()
    if found is not None:
        return bytes(found.data) if found.data is not None else None
    answer = await hub.tile(z, x, y)
    if answer.get("failed"):
        raise Unavailable(answer["failed"])
    data = base64.b64decode(answer["tile"]) if answer.get("tile") else None
    await connection.execute(
        text("""
            insert into travel.travel_tile (z, x, y, data, build)
            values (:z, :x, :y, :data, :build)
            on conflict (z, x, y) do nothing
        """),
        {"z": z, "x": x, "y": y, "data": data, "build": answer.get("build")},
    )
    return data


class Stop(BaseModel):
    type: Literal["stay", "block"]
    id: str
    number: int | None
    title: str
    lon: float
    lat: float


class Leg(BaseModel):
    distance_m: int
    duration_s: int


class DayRoute(BaseModel):
    day: date
    profile: Profile
    stops: list[Stop]
    line: list[list[float]] | None
    legs: list[Leg]
    distance_m: int | None
    duration_s: int | None
    failed: str | None


async def day_route(
    connection: AsyncConnection, trip_id: str, day: date, profile: Profile
) -> DayRoute:
    found = await itinerary.itinerary(connection, trip_id)
    today = next((one for one in found.days if one.day == day), None)
    if today is None:
        raise itinerary.travel.NotFound(f"el día {day.isoformat()} del viaje")
    stops: list[Stop] = []
    previous = next((one for one in found.days if one.number == today.number - 1), None)
    woke = previous.sleeping if previous else None
    if woke and woke.place.lat is not None and woke.place.lon is not None:
        stops.append(
            Stop(
                type="stay",
                id=woke.id,
                number=None,
                title=woke.accommodation or woke.place.name,
                lon=woke.place.lon,
                lat=woke.place.lat,
            )
        )
    number = 0
    for item in today.items:
        block = item.block
        if block is None or block.place is None or block.place.lat is None:
            continue
        number += 1
        stops.append(
            Stop(
                type="block",
                id=block.id,
                number=number,
                title=block.title,
                lon=block.place.lon,
                lat=block.place.lat,
            )
        )
    sleeps = today.sleeping
    if sleeps and sleeps.place.lat is not None and sleeps.place.lon is not None:
        last = stops[-1] if stops else None
        if not last or (last.lon, last.lat) != (sleeps.place.lon, sleeps.place.lat):
            stops.append(
                Stop(
                    type="stay",
                    id=sleeps.id,
                    number=None,
                    title=sleeps.accommodation or sleeps.place.name,
                    lon=sleeps.place.lon,
                    lat=sleeps.place.lat,
                )
            )
    empty = DayRoute(
        day=day,
        profile=profile,
        stops=stops,
        line=None,
        legs=[],
        distance_m=None,
        duration_s=None,
        failed=None,
    )
    if len(stops) < 2:
        return empty
    answer = await hub.directions(profile, [(one.lon, one.lat) for one in stops][:25])
    route = answer.get("route")
    if not route:
        return empty.model_copy(update={"failed": answer.get("failed") or "sin ruta"})
    return empty.model_copy(
        update={
            "line": route["geometry"],
            "legs": [Leg(**leg) for leg in route["legs"]],
            "distance_m": route["distance_m"],
            "duration_s": route["duration_s"],
        }
    )
