from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from travel import geo, travel

KINDS = {"countries": "kpi", "last_trip": "upnext", "next_trip": "upnext", "by_year": "bars"}

YEARS = 8


async def countries(connection: AsyncConnection) -> dict:
    trips = travel.lived(await travel.all_trips(connection))
    areas = travel.areas_visited(trips, "country", await travel.other_places(connection))
    if not areas:
        return envelope(KINDS["countries"], "empty", {"detail": "aún no hay viajes"})
    europe = sum(1 for area in areas if area.code in geo.EUROPE)
    return envelope(
        KINDS["countries"],
        "ready",
        {
            "value": len(areas),
            "unit": "países",
            "icon": "globe",
            "detail": f"{europe} de {len(geo.EUROPE)} de Europa",
        },
    )


async def last_trip(connection: AsyncConnection) -> dict:
    done = [one for one in travel.lived(await travel.all_trips(connection)) if not one.archived]
    if not done:
        return envelope(KINDS["last_trip"], "empty", {"detail": "aún no hay viajes"})
    last = done[0]
    places = " · ".join(dict.fromkeys(stay.place.name for stay in last.stays)) or None
    nights = f"{last.nights} noche{'s' if last.nights != 1 else ''}"
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


PHASES = {"plan": "plan", "upcoming": "confirmado", "ongoing": "en curso"}


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
        return envelope(KINDS["next_trip"], "empty", {"detail": "ningún viaje a la vista"})
    found = ahead[0]
    places = " · ".join(dict.fromkeys(stay.place.name for stay in found.stays)) or None
    days = f"{found.days} día{'s' if found.days != 1 else ''}"
    detail = " · ".join(part for part in (PHASES[found.phase], days, places) if part)
    return envelope(
        KINDS["next_trip"],
        "ready",
        {"events": [{"at": found.starts_on.isoformat(), "title": found.title, "detail": detail}]},
    )


async def by_year(connection: AsyncConnection) -> dict:
    figures = travel.stats(travel.lived(await travel.all_trips(connection)))
    if not figures.by_year:
        return envelope(KINDS["by_year"], "empty", {"detail": "aún no hay viajes"})
    first = max(figures.by_year[0].year, figures.by_year[-1].year - YEARS + 1)
    counted = {row.year: row.trips for row in figures.by_year}
    years = list(range(first, max(figures.by_year[-1].year, date.today().year) + 1))[-YEARS:]
    series = [float(counted.get(year, 0)) for year in years]
    return envelope(
        KINDS["by_year"],
        "ready",
        {
            "value": int(series[-1]),
            "unit": "viajes",
            "series": series,
            "labels": [f"’{str(year)[2:]}" for year in years],
            "highlight": len(years) - 1,
            "detail": f"{figures.trips} viajes · {figures.nights} noches fuera",
        },
    )


RENDERERS = {
    "countries": countries,
    "last_trip": last_trip,
    "next_trip": next_trip,
    "by_year": by_year,
}
