from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from travel import ideas, travel

MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
LIVE = ("plan", "upcoming", "ongoing")

OUT = text("""
    select plan_id, payload from (
        select distinct on (payload->>'plan_id') payload->>'plan_id' as plan_id, payload
        from travel.travel_outbox
        where type = 'travel.plan'
        order by payload->>'plan_id', id desc
    ) last
    where not coalesce((payload->'trip'->>'removed')::boolean, false)
""")


def _trip(found: travel.Trip) -> dict:
    people = f"{found.travellers} viajero{'s' if found.travellers != 1 else ''}"
    return contracts.trip(
        id=f"trip:{found.id}",
        title=found.title,
        phase=found.phase,
        href=f"/travel/viajes/{found.id}",
        starts_on=found.starts_on,
        ends_on=found.ends_on,
        image=f"/api/travel/trips/{found.id}/cover?size=thumb&v={found.cover.version}"
        if found.cover
        else None,
        detail=f"{found.days} días · {people}",
    )


def _idea(found: ideas.Idea) -> dict:
    parts = []
    if found.months:
        parts.append(" o ".join(MONTHS[month - 1] for month in found.months[:3]))
    if found.days_min or found.days_max:
        low, high = found.days_min or found.days_max, found.days_max or found.days_min
        parts.append(f"{low} días" if low == high else f"{low}–{high} días")
    if found.budget_eur is not None:
        parts.append(f"{round(found.budget_eur)} € por persona")
    return contracts.trip(
        id=f"idea:{found.id}",
        title=found.title,
        phase="idea",
        href=f"/travel/ideas/{found.id}",
        detail=" · ".join(parts)[:200],
    )


async def current(connection: AsyncConnection) -> dict[str, dict]:
    found: dict[str, dict] = {}
    going: set[str] = set()
    for one in await travel.all_trips(connection):
        if one.archived or one.phase not in LIVE or not one.mine:
            continue
        found[f"trip:{one.id}"] = _trip(one)
        if one.idea_id:
            going.add(one.idea_id)
    for one in await ideas.ideas(connection):
        if one.archived or one.id in going or not one.mine:
            continue
        found[f"idea:{one.id}"] = _idea(one)
    return found


async def refresh(connection: AsyncConnection) -> int:
    wanted = await current(connection)
    queued = 0
    for plan_id, item in wanted.items():
        payload = {"plan_id": plan_id, contracts.TRIP: item}
        last = await travel._last_of(connection, plan_id, "plan")
        if last is not None and last[1] == payload:
            continue
        await travel._enqueue(connection, plan_id, payload, kind="plan")
        queued += 1
    for row in (await connection.execute(OUT)).all():
        if row.plan_id in wanted:
            continue
        payload = json.loads(row.payload) if isinstance(row.payload, str) else row.payload
        await travel._enqueue(
            connection,
            row.plan_id,
            {"plan_id": row.plan_id, contracts.TRIP: {**payload[contracts.TRIP], "removed": True}},
            kind="plan",
        )
        queued += 1
    return queued


async def make_idea(connection: AsyncConnection, asked: contracts.TripIdea) -> dict:
    title = " ".join(asked.title.split())
    for one in await ideas.ideas(connection):
        if not one.archived and one.title.casefold() == title.casefold():
            return contracts.trip_idea_made(id=one.id, href=f"/travel/ideas/{one.id}", already=True)
    made = await ideas.create_idea(
        connection, ideas.IdeaIn(title=title, notes=asked.notes), source="app"
    )
    if asked.place:
        place = await travel.save_place(
            connection, travel.PlaceIn(name=asked.place, lat=asked.lat, lon=asked.lon)
        )
        await ideas.add_place(connection, made.id, place.id)
    return contracts.trip_idea_made(id=made.id, href=f"/travel/ideas/{made.id}", already=False)
