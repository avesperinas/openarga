from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from outings import hub, wishes

CONTRACT = contracts.TRIP

LATEST = text(f"""
    select distinct on (module, payload->'{CONTRACT}'->>'id')
        module, payload->'{CONTRACT}' as item
    from outings.events
    where payload ? '{CONTRACT}'
    order by module, payload->'{CONTRACT}'->>'id', ts desc, ingested_at desc
""")

ORDER = {"ongoing": 0, "upcoming": 1, "plan": 2, "idea": 3}


class Planned(BaseModel):
    app: str
    id: str
    title: str
    phase: str
    href: str
    starts_on: date | None
    ends_on: date | None
    image: str | None
    detail: str


async def planned(connection: AsyncConnection) -> list[Planned]:
    found: list[Planned] = []
    for row in (await connection.execute(LATEST)).all():
        item = row.item
        if item.get("removed") or item.get("phase") not in ORDER:
            continue
        found.append(
            Planned(
                app=row.module,
                id=item["id"],
                title=item["title"],
                phase=item["phase"],
                href=item["href"],
                starts_on=date.fromisoformat(item["starts_on"]) if item.get("starts_on") else None,
                ends_on=date.fromisoformat(item["ends_on"]) if item.get("ends_on") else None,
                image=item.get("image"),
                detail=item.get("detail", ""),
            )
        )
    found.sort(key=lambda one: (ORDER[one.phase], one.starts_on or date.max, one.title.casefold()))
    return found


class Idea(BaseModel):
    href: str
    already: bool


async def to_idea(connection: AsyncConnection, wish_id: str) -> Idea:
    found = await wishes.wish(connection, wish_id)
    if found.kind != "trip":
        raise wishes.Conflict("solo un viaje pasa a idea", "NOT_A_TRIP")
    body: dict = {"title": found.name[:120]}
    if found.place is not None:
        body["place"] = (found.place.name or found.name)[:120]
        if found.place.lat is not None and found.place.lon is not None:
            body |= {"lat": found.place.lat, "lon": found.place.lon}
    if found.body:
        body["notes"] = found.body[:2000]
    made = await hub.capability(contracts.TRIPS_IDEA, contracts.trip_idea(**body))
    return Idea(href=made["href"], already=bool(made.get("already")))
