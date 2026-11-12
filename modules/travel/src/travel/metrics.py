from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import metrics as cifras
from travel import travel

APP = "travel"
MADRID = ZoneInfo("Europe/Madrid")


def _point(key: str, label: str, kind: str, day: date, value: float) -> dict[str, Any]:
    return contracts.metric(
        APP, key=f"{APP}.{key}", label=label, unit="count", kind=kind, day=day, value=value
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    trips = sorted(travel.lived(await travel.all_trips(connection)), key=lambda one: one.ends_on)
    found: list[dict[str, Any]] = []
    trips_per_day: dict[date, int] = {}
    for trip in trips:
        trips_per_day[trip.ends_on] = trips_per_day.get(trip.ends_on, 0) + 1
    found += [_point("trips", "Viajes", "amount", day, n) for day, n in trips_per_day.items()]
    for trip in trips:
        found += [
            _point("days_away", "Días de viaje", "amount", trip.starts_on + timedelta(days=n), 1)
            for n in range(travel.days_of(trip.starts_on, trip.ends_on))
        ]

    seen = {
        one.place.country_code
        for one in await travel.other_places(connection)
        if one.place.country_code
    }
    counted: dict[date, int] = {}
    last = None
    for trip in trips:
        seen |= set(trip.countries)
        if len(seen) != last:
            counted[trip.ends_on] = last = len(seen)
    found += [
        _point("countries", "Países visitados", "level", day, n) for day, n in counted.items()
    ]
    if not trips and seen:
        today = datetime.now(UTC).astimezone(MADRID).date()
        found += await cifras.steady(
            connection, APP, [_point("countries", "Países visitados", "level", today, len(seen))]
        )
    return found
