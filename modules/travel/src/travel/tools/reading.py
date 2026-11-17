from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    hub,
    journal,
    money,
    today,
    travel,
)
from travel.tools.common import _detail, _hhmm, _in_range, _place, _summary


class GetTrips(BaseModel):
    since: date | None = Field(default=None, description="Only those ending on this day or later.")
    until: date | None = Field(default=None, description="Only those starting up to this day.")
    country: str | None = Field(
        default=None, min_length=2, max_length=2, description="ISO 3166-1 alfa-2: `IT`, `BE`."
    )
    tag: str | None = Field(default=None, max_length=40)
    companion: str | None = Field(default=None, max_length=60)
    include_archived: bool = Field(
        default=False,
        description=(
            "Also the archived ones, which the Trips list hides. They still count in the figures "
            "and in what was visited."
        ),
    )
    phase: list[travel.Phase] | None = Field(
        default=None,
        description=(
            "Only those in these phases: plan, upcoming (confirmed, still to come), ongoing, done."
            " If not given, all."
        ),
    )
    limit: int = Field(default=50, ge=1, le=300)


async def get_trips(connection: AsyncConnection, arguments: GetTrips) -> dict[str, Any]:
    trips = [
        one
        for one in await travel.all_trips(connection)
        if arguments.include_archived or not one.archived
    ]
    tag = arguments.tag.lower() if arguments.tag else None
    companion = arguments.companion.lower() if arguments.companion else None
    found = [
        one
        for one in trips
        if _in_range(one, arguments.since, arguments.until)
        and (arguments.phase is None or one.phase in arguments.phase)
        and (arguments.country is None or arguments.country.upper() in one.countries)
        and (tag is None or tag in (t.lower() for t in one.tags))
        and (companion is None or any(companion in c.lower() for c in one.companions))
    ]
    return {"total": len(found), "trips": [_summary(one) for one in found[: arguments.limit]]}


class GetTrip(BaseModel):
    trip_id: str | None = Field(default=None, description="The id `get_trips` gives.")
    title: str | None = Field(
        default=None, max_length=120, description="Or part of the title, if the id is not known."
    )

    @model_validator(mode="after")
    def one_of(self) -> GetTrip:
        if not self.trip_id and not self.title:
            raise ValueError("the trip's id or part of its title is needed")
        return self


async def _pick(connection: AsyncConnection, trip_id: str | None, title: str | None) -> dict:
    if trip_id:
        try:
            return {"trip": await travel.trip(connection, trip_id)}
        except travel.NotFound:
            return {"error": f"there is no trip with id {trip_id}", "code": "NOT_FOUND"}
    needle = (title or "").lower()
    matches = [one for one in await travel.all_trips(connection) if needle in one.title.lower()]
    if len(matches) == 1:
        return {"trip": matches[0]}
    if not matches:
        return {"error": f'no trip is called "{title}"', "code": "NOT_FOUND"}
    return {
        "error": "several trips match; say which with its trip_id",
        "code": "AMBIGUOUS",
        "candidates": [_summary(one) for one in matches[:10]],
    }


async def get_trip(connection: AsyncConnection, arguments: GetTrip) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    found = await money.travellers(connection, picked["trip"].id)
    return {
        **_detail(picked["trip"]),
        "people": [{"traveller_id": one.id, "name": one.name, "me": one.me} for one in found],
        "journal": [
            {"day": one.day.isoformat(), "text": one.body}
            for one in await journal.entries(connection, picked["trip"].id)
        ],
    }


class GetPlacesVisited(BaseModel):
    level: Literal["country", "region"] = "country"
    since: date | None = None
    until: date | None = None


async def _others_if_undated(
    connection: AsyncConnection, since: date | None, until: date | None
) -> list[travel.OtherPlace]:
    if since is not None or until is not None:
        return []
    return await travel.other_places(connection)


async def get_places_visited(
    connection: AsyncConnection, arguments: GetPlacesVisited
) -> dict[str, Any]:
    trips = [
        one
        for one in travel.lived(await travel.all_trips(connection))
        if _in_range(one, arguments.since, arguments.until)
    ]
    others = await _others_if_undated(connection, arguments.since, arguments.until)
    areas = travel.areas_visited(trips, arguments.level, others)
    return {
        "level": arguments.level,
        "total": len(areas),
        "areas": [
            {
                "code": area.code,
                "name": area.name,
                "slept": area.slept,
                "trips": area.trips,
                "nights": area.nights,
                "first_visit": area.first.isoformat() if area.first else None,
                "last_visit": area.last.isoformat() if area.last else None,
                "places": area.places,
            }
            for area in areas
        ],
    }


class SummariseTravel(BaseModel):
    group_by: Literal["year", "country", "mode"] = "year"
    since: date | None = None
    until: date | None = None


async def summarise_travel(
    connection: AsyncConnection, arguments: SummariseTravel
) -> dict[str, Any]:
    trips = [
        one
        for one in travel.lived(await travel.all_trips(connection))
        if _in_range(one, arguments.since, arguments.until)
    ]
    others = await _others_if_undated(connection, arguments.since, arguments.until)
    figures = travel.stats(trips, others)
    totals = {
        "trips": figures.trips,
        "nights": figures.nights,
        "km": figures.km,
        "countries": figures.countries,
        "europe_visited": f"{len(figures.europe_visited)} of {figures.europe_total}",
        "average_cost_per_day_eur": figures.average_cost_per_day,
    }
    if arguments.group_by == "year":
        groups: list[dict[str, Any]] = [row.model_dump() for row in figures.by_year]
    elif arguments.group_by == "mode":
        groups = [{"mode": mode, "km": km} for mode, km in figures.km_by_mode.items() if km]
    else:
        per_night = {row["code"]: row["per_night"] for row in figures.spend_per_night_by_country}
        groups = [
            {
                "country": area.code,
                "name": area.name,
                "trips": area.trips,
                "nights": area.nights,
                "spend_per_night_eur": per_night.get(area.code),
            }
            for area in travel.areas_visited(trips, "country", others)
        ]
    return {"group_by": arguments.group_by, "totals": totals, "groups": groups}


class GetOtherPlaces(BaseModel):
    pass


def _other(other: travel.OtherPlace) -> dict[str, Any]:
    return {"other_place_id": other.id, **_place(other.place), "note": other.note}


async def get_other_places(connection: AsyncConnection, arguments: GetOtherPlaces) -> dict:
    found = await travel.other_places(connection)
    return {"total": len(found), "other_places": [_other(one) for one in found]}


class FindPlace(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=120,
        description=(
            "The place as one would say it, with the country if it can be confused: `Bruges`, "
            "`Santiago, Chile`, `Prado Museum`."
        ),
    )
    limit: int = Field(default=5, ge=1, le=10)


async def find_place(connection: AsyncConnection, arguments: FindPlace) -> dict[str, Any]:
    saved = await travel.places(connection, arguments.query)
    found = await hub.search(arguments.query, arguments.limit)
    return {
        "saved": [_place(place) for place in saved[:5]],
        "candidates": [
            {
                key: candidate.get(key)
                for key in (
                    "name",
                    "display_name",
                    "lat",
                    "lon",
                    "kind",
                    "osm_type",
                    "osm_id",
                    "country_code",
                    "region_code",
                    "country",
                    "region",
                )
            }
            | {"category": travel.category_of(candidate.get("kind"))}
            for candidate in found.get("candidates", [])
        ],
        "failed": found.get("failed", []),
    }


class FindNearby(BaseModel):
    place_id: str | None = Field(
        default=None,
        description=(
            "Near this stored place: the place_id of a main place, a visit or a block, as get_trip"
            " gives them (with include itinerary)."
        ),
    )
    lat: float | None = Field(default=None, ge=-90, le=90, description="Or near this point.")
    lon: float | None = Field(default=None, ge=-180, le=180)
    kind: Literal["food", "sights", "nature", "shopping", "nightlife"] = Field(
        default="sights",
        description=(
            "sights (what to see), food (where to eat), nature (parks, beaches, natural "
            "viewpoints), shopping or nightlife."
        ),
    )
    radius: int = Field(default=1000, ge=100, le=3000, description="In metres, up to 3000.")
    limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def somewhere(self) -> FindNearby:
        if self.place_id is None and (self.lat is None or self.lon is None):
            raise ValueError("a place_id or lat and lon is needed")
        return self


async def find_nearby(connection: AsyncConnection, arguments: FindNearby) -> dict[str, Any]:
    lat, lon = arguments.lat, arguments.lon
    if arguments.place_id:
        try:
            place = await travel.place_by_id(connection, arguments.place_id)
        except travel.NotFound:
            return {
                "error": f"there is no place with id {arguments.place_id}",
                "code": "NOT_FOUND",
            }
        if place.lat is None or place.lon is None:
            return {"error": "that place is not located on the map", "code": "INVALID"}
        lat, lon = place.lat, place.lon
    assert lat is not None and lon is not None
    found = await hub.nearby(lat, lon, arguments.kind, arguments.radius, arguments.limit)
    return {
        "center": {"lat": lat, "lon": lon},
        "candidates": [
            {
                key: one.get(key)
                for key in (
                    "name",
                    "local_name",
                    "display_name",
                    "lat",
                    "lon",
                    "kind",
                    "osm_type",
                    "osm_id",
                    "distance_m",
                    "country_code",
                    "region_code",
                    "cuisine",
                    "website",
                    "opening_hours",
                )
            }
            for one in found["places"]
        ],
        "failed": found["failed"],
    }


class GetToday(BaseModel):
    day: date | None = Field(
        default=None,
        description=(
            "The day asked about, where the person is. If not given, today in the person's zone: "
            "when travelling far, say it if it is already another day there."
        ),
    )


async def get_today(connection: AsyncConnection, arguments: GetToday) -> dict[str, Any]:
    found = await today.today(connection, arguments.day)
    if found.trip is None:
        upcoming = found.next_trip
        return {
            "day": found.day.isoformat(),
            "trip": None,
            "next_trip": {
                "trip_id": upcoming.id,
                "title": upcoming.title,
                "starts_on": upcoming.starts_on.isoformat(),
                "phase": upcoming.phase,
                "days_to_go": (upcoming.starts_on - found.day).days,
            }
            if upcoming
            else None,
        }
    return {
        "day": found.day.isoformat(),
        "trip": {
            "trip_id": found.trip.id,
            "title": found.trip.title,
            "day_number": found.trip.number,
            "days": found.trip.days,
        },
        "sleeping": found.sleeping,
        "journal": found.journal,
        "entries": [
            {
                "type": one.type,
                "id": one.id,
                "title": one.title,
                "detail": one.detail,
                "kind": one.kind,
                "starts_at": _hhmm(one.starts_at),
                "ends_at": _hhmm(one.ends_at),
                "where": {"name": one.where.name, "lat": one.where.lat, "lon": one.where.lon}
                if one.where
                else None,
                "confirmation": one.confirmation,
            }
            for one in found.entries
        ],
    }


class GetWeather(BaseModel):
    place_id: str | None = Field(default=None, description="A stored place.")
    lat: float | None = Field(default=None, ge=-90, le=90, description="Or a point.")
    lon: float | None = Field(default=None, ge=-180, le=180)
    kind: Literal["forecast", "climate"] = Field(
        default="forecast",
        description="forecast, the next 16 days; climate, each month on average.",
    )

    @model_validator(mode="after")
    def somewhere(self) -> GetWeather:
        if self.place_id is None and (self.lat is None or self.lon is None):
            raise ValueError("a place_id or lat and lon is needed")
        return self


async def get_weather(connection: AsyncConnection, arguments: GetWeather) -> dict[str, Any]:
    lat, lon, name = arguments.lat, arguments.lon, None
    if arguments.place_id:
        try:
            place = await travel.place_by_id(connection, arguments.place_id)
        except travel.NotFound:
            return {
                "error": f"there is no place with id {arguments.place_id}",
                "code": "NOT_FOUND",
            }
        if place.lat is None or place.lon is None:
            return {"error": "that place is not located on the map", "code": "INVALID"}
        lat, lon, name = place.lat, place.lon, place.name
    assert lat is not None and lon is not None
    found = await (
        hub.forecast(lat, lon) if arguments.kind == "forecast" else hub.climate(lat, lon)
    )
    return {"place": name, "kind": arguments.kind, **found}
