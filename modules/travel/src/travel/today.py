from __future__ import annotations

from datetime import date, time
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import itinerary, journal, travel

Kind = Literal["check_out", "leg", "check_in", "block"]
TRAVEL_MODES = {"plane": "driving", "train": "transit", "car": "driving", "bus": "transit"}


class Where(BaseModel):
    name: str
    lat: float
    lon: float
    google: str
    apple: str


class Entry(BaseModel):
    type: Kind
    id: str
    title: str
    detail: str | None
    kind: str | None
    starts_at: time | None
    ends_at: time | None
    where: Where | None
    confirmation: str | None


class TripToday(BaseModel):
    id: str
    title: str
    number: int
    days: int
    day_title: str | None = None


class Today(BaseModel):
    day: date
    trip: TripToday | None
    sleeping: str | None
    entries: list[Entry]
    here: tuple[float, float] | None = None
    next_trip: travel.TripSummary | None = None
    journal: str | None = None


def where(name: str, lat: float | None, lon: float | None, mode: str = "walking") -> Where | None:
    if lat is None or lon is None:
        return None
    point = f"{lat:.6f},{lon:.6f}"
    flags = {"walking": "w", "driving": "d", "transit": "r"}
    return Where(
        name=name,
        lat=lat,
        lon=lon,
        google=f"https://www.google.com/maps/dir/?api=1&destination={point}&travelmode={mode}",
        apple=f"https://maps.apple.com/?daddr={point}&q={quote(name)}&dirflg={flags[mode]}",
    )


def chronological(entries: list[Entry]) -> list[Entry]:
    keyed = []
    last = time.min
    for index, entry in enumerate(entries):
        if entry.starts_at is not None:
            last = entry.starts_at
        keyed.append((entry.starts_at or last, entry.starts_at is None, index, entry))
    return [entry for *_, entry in sorted(keyed, key=lambda one: one[:3])]


def _entries(day: itinerary.Day) -> list[Entry]:
    found: list[Entry] = []
    for item in day.items:
        if item.type in ("check_out", "check_in") and item.stay:
            stay = item.stay
            leaving = item.type == "check_out"
            name = stay.accommodation or stay.place.name
            found.append(
                Entry(
                    type=item.type,
                    id=stay.id,
                    title=f"{'Sales de' if leaving else 'Llegas a'} {name}",
                    detail=stay.address or (stay.place.name if stay.accommodation else None),
                    kind=None,
                    starts_at=stay.check_out_at if leaving else stay.check_in_at,
                    ends_at=None,
                    where=None if leaving else where(name, stay.place.lat, stay.place.lon),
                    confirmation=stay.confirmation,
                )
            )
        elif item.type == "leg" and item.leg:
            leg = item.leg
            ticket = " ".join(part for part in (leg.carrier, leg.number) if part)
            found.append(
                Entry(
                    type="leg",
                    id=leg.id,
                    title=f"{leg.from_place.name} → {leg.to_place.name}",
                    detail=" · ".join(
                        part
                        for part in (
                            ticket or None,
                            f"terminal {leg.terminal}" if leg.terminal else None,
                            f"asiento {leg.seat}" if leg.seat else None,
                        )
                        if part
                    )
                    or None,
                    kind=leg.mode,
                    starts_at=leg.departs_at,
                    ends_at=leg.arrives_at if leg.arrives_on in (None, leg.travelled_on) else None,
                    where=where(
                        leg.from_place.name,
                        leg.from_place.lat,
                        leg.from_place.lon,
                        TRAVEL_MODES.get(leg.mode, "walking"),
                    ),
                    confirmation=leg.confirmation,
                )
            )
        elif item.block:
            block = item.block
            place = block.place
            found.append(
                Entry(
                    type="block",
                    id=block.id,
                    title=block.title,
                    detail=block.notes,
                    kind=block.kind,
                    starts_at=block.starts_at,
                    ends_at=block.ends_at,
                    where=where(block.title, place.lat, place.lon) if place else None,
                    confirmation=block.confirmation,
                )
            )
    return found


async def today(connection: AsyncConnection, day: date | None = None) -> Today:
    on = day or travel.today()
    trips = await travel.all_trips(connection)
    going = [
        one
        for one in trips
        if one.status == "confirmed" and one.starts_on <= on <= one.ends_on and not one.archived
    ]
    if not going:
        ahead = sorted(
            (one for one in trips if one.starts_on > on and not one.archived),
            key=lambda one: one.starts_on,
        )
        return Today(
            day=on,
            trip=None,
            sleeping=None,
            entries=[],
            next_trip=travel.TripSummary(**ahead[0].model_dump()) if ahead else None,
        )
    current = sorted(going, key=lambda one: one.starts_on)[0]
    found = await itinerary.itinerary(connection, current.id)
    this = next(one for one in found.days if one.day == on)
    entries = chronological(_entries(this))
    here = None
    if (
        this.sleeping
        and this.sleeping.place.lat is not None
        and this.sleeping.place.lon is not None
    ):
        here = (this.sleeping.place.lat, this.sleeping.place.lon)
    else:
        located = next((one.where for one in entries if one.where), None)
        here = (located.lat, located.lon) if located else None
    written = await journal.entry(connection, current.id, on)
    return Today(
        day=on,
        journal=written.body if written else None,
        trip=TripToday(
            id=current.id,
            title=current.title,
            number=this.number,
            days=current.days,
            day_title=this.title,
        ),
        sleeping=(this.sleeping.accommodation or this.sleeping.place.name)
        if this.sleeping
        else None,
        entries=entries,
        here=here,
    )
