from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from outings import agenda, places, wishes
from outings.common import today


class WishPoint(BaseModel):
    id: str
    name: str
    kind: wishes.Kind
    lat: float
    lon: float
    has_photo: bool
    photo_version: str | None
    where: str | None


class EventPoint(BaseModel):
    id: str
    title: str
    starts_on: date
    ends_on: date
    category: agenda.Category
    lat: float
    lon: float
    where: str | None


class MapOut(BaseModel):
    wishes: list[WishPoint]
    events: list[EventPoint]


class Near(BaseModel):
    id: str
    name: str
    kind: Literal["eat", "plan", "getaway", "trip"]
    km: float


def _where(*parts: str | None) -> str | None:
    found = [part for part in parts if part]
    return " · ".join(dict.fromkeys(found)) or None


async def points(connection: AsyncConnection, days: int = 30) -> MapOut:
    found = [
        WishPoint(
            id=one.id,
            name=one.name,
            kind=one.kind,
            lat=one.place.lat,
            lon=one.place.lon,
            has_photo=one.has_photo,
            photo_version=one.photo_version,
            where=_where(one.place.town, one.place.country),
        )
        for one in await wishes.wishes(connection)
        if one.place and one.place.lat is not None and one.place.lon is not None
    ]
    first = today()
    coming = [
        EventPoint(
            id=one.id,
            title=one.title,
            starts_on=one.starts_on,
            ends_on=one.ends_on,
            category=one.category,
            lat=one.lat,
            lon=one.lon,
            where=_where(one.venue, one.town),
        )
        for one in await agenda.events(connection, first, first + timedelta(days=days))
        if one.lat is not None and one.lon is not None
    ]
    return MapOut(wishes=found, events=coming)


async def near(connection: AsyncConnection, lat: float, lon: float) -> list[Near]:
    out = []
    for one in await wishes.wishes(connection):
        if not one.place or one.place.lat is None or one.place.lon is None:
            continue
        distance = places.km((lat, lon), (one.place.lat, one.place.lon))
        if distance <= places.NEAR_KM:
            out.append(Near(id=one.id, name=one.name, kind=one.kind, km=round(distance, 1)))
    return sorted(out, key=lambda one: one.km)
