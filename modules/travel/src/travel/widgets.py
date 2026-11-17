from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from travel import geo, travel
from travel.words import counted, say

KINDS = {"countries": "kpi", "last_trip": "upnext", "next_trip": "upnext", "by_year": "bars"}

YEARS = 8


async def countries(connection: AsyncConnection) -> dict:
    trips = travel.lived(await travel.all_trips(connection))
    areas = travel.areas_visited(trips, "country", await travel.other_places(connection))
    if not areas:
        return envelope(KINDS["countries"], "empty", {"detail": say("widget.no_trips")})
    europe = sum(1 for area in areas if area.code in geo.EUROPE)
    return envelope(
        KINDS["countries"],
        "ready",
        {
            "value": len(areas),
            "unit": say("widget.countries_unit"),
            "icon": "globe",
            "detail": say("widget.of_europe", count=europe, total=len(geo.EUROPE)),
        },
    )


async def last_trip(connection: AsyncConnection) -> dict:
    done = [one for one in travel.lived(await travel.all_trips(connection)) if not one.archived]
    if not done:
        return envelope(KINDS["last_trip"], "empty", {"detail": say("widget.no_trips")})
    last = done[0]
    places = " · ".join(dict.fromkeys(stay.place.name for stay in last.stays)) or None
    nights = counted("widget.nights", last.nights)
    return envelope(
        KINDS["last_trip"],
        "ready",
        {
            "events": [
                {
                    "at": last.starts_on.isoformat(),
                    "title": last.title,
                    "detail": f"{nights} · {places}" if places else nights,
                }
            ]
        },
    )


async def next_trip(connection: AsyncConnection) -> dict:
    today = travel.today()
    ahead = sorted(
        (
            one
            for one in await travel.all_trips(connection)
            if not one.archived
            and (one.phase == "ongoing" or (one.phase != "done" and one.starts_on >= today))
        ),
        key=lambda one: (one.phase != "ongoing", one.starts_on),
    )
    if not ahead:
        return envelope(KINDS["next_trip"], "empty", {"detail": say("widget.no_trip_ahead")})
    found = ahead[0]
    places = " · ".join(dict.fromkeys(stay.place.name for stay in found.stays)) or None
    days = counted("widget.days", found.days)
    detail = " · ".join(part for part in (say(f"phase.{found.phase}"), days, places) if part)
    return envelope(
        KINDS["next_trip"],
        "ready",
        {"events": [{"at": found.starts_on.isoformat(), "title": found.title, "detail": detail}]},
    )


async def by_year(connection: AsyncConnection) -> dict:
    figures = travel.stats(travel.lived(await travel.all_trips(connection)))
    if not figures.by_year:
        return envelope(KINDS["by_year"], "empty", {"detail": say("widget.no_trips")})
    first = max(figures.by_year[0].year, figures.by_year[-1].year - YEARS + 1)
    per_year = {row.year: row.trips for row in figures.by_year}
    years = list(range(first, max(figures.by_year[-1].year, date.today().year) + 1))[-YEARS:]
    series = [float(per_year.get(year, 0)) for year in years]
    return envelope(
        KINDS["by_year"],
        "ready",
        {
            "value": int(series[-1]),
            "unit": say("widget.trips_unit"),
            "series": series,
            "labels": [f"’{str(year)[2:]}" for year in years],
            "highlight": len(years) - 1,
            "detail": say("widget.trips_nights", trips=figures.trips, nights=figures.nights),
        },
    )


RENDERERS = {
    "countries": countries,
    "last_trip": last_trip,
    "next_trip": next_trip,
    "by_year": by_year,
}
