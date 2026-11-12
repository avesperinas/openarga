from __future__ import annotations

import math
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from outings import hub, profile

PER_PASS = 6
NEAR_KM = 15.0

PENDING = text("""
    select distinct coalesce(e.venue, e.town) as name, coalesce(e.town, '') as town
    from outings.outings_event e
    where not e.hidden and e.ends_on >= current_date and coalesce(e.venue, e.town) is not null
      and not exists (
          select 1 from outings.outings_venue v
          where v.name = coalesce(e.venue, e.town) and v.town = coalesce(e.town, '')
      )
    limit :limit
""")

SAVE = text("""
    insert into outings.outings_venue (name, town, lat, lon, found)
    values (:name, :town, :lat, :lon, :found)
    on conflict (user_id, name, town) do nothing
""")


def queries(name: str, town: str) -> list[str]:
    place = name.split("·")[0].split(" - ")[0].strip()
    suffix = profile.current().geocoding
    asked = []
    if town and place.casefold() != town.casefold():
        asked.append(f"{place}, {town}, {suffix}")
    asked.append(f"{town or place}, {suffix}")
    return list(dict.fromkeys(asked))


async def locate(connection: AsyncConnection, limit: int = PER_PASS) -> int:
    rows = (await connection.execute(PENDING, {"limit": limit})).all()
    asked = 0
    for row in rows:
        found: dict[str, Any] | None = None
        failed = False
        for query in queries(row.name, row.town):
            answer = await hub.search(query, limit=1)
            if answer.get("failed"):
                failed = True
                break
            if answer.get("candidates"):
                found = answer["candidates"][0]
                break
        if failed:
            break
        asked += 1
        await connection.execute(
            SAVE,
            {
                "name": row.name[:200],
                "town": row.town[:120],
                "lat": found.get("lat") if found else None,
                "lon": found.get("lon") if found else None,
                "found": found is not None and found.get("lat") is not None,
            },
        )
    return asked


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(h))
