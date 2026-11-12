from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_agenda import KEY, dated, uid
from arga_tenancy import CURRENT_USER_SQL as ME
from travel.travel.common import Conflict, NotFound
from travel.travel.models import Leg, Trip
from travel.travel.places import PLACE_COLUMNS, PlaceIn, save_place
from travel.travel.read import trip


async def _touch(connection: AsyncConnection, trip_id: str) -> None:
    updated = await connection.execute(
        text("update travel.travel_trip set updated_at = now() where id = :id"), {"id": trip_id}
    )
    if updated.rowcount == 0:
        raise NotFound(f"viaje {trip_id}")
    from travel import itinerary

    await itinerary.ensure_blocks(connection, trip_id)
    for statement in SPREAD:
        await connection.execute(text(statement), {"id": trip_id})
    await enqueue(connection, await trip(connection, trip_id))


PARTS_OF_TRIP = (
    "travel_stay",
    "travel_visit",
    "travel_leg",
    "travel_expense",
    "travel_block",
    "travel_traveller",
    "travel_expense_share",
    "travel_settlement",
    "travel_note",
    "travel_check_item",
    "travel_document",
    "travel_day",
    "travel_cover",
)

PLACES_OF_TRIP = """
    select place_id from travel.travel_stay where trip_id = :id
    union select place_id from travel.travel_visit where trip_id = :id
    union select from_place_id from travel.travel_leg where trip_id = :id
    union select to_place_id from travel.travel_leg where trip_id = :id
    union select place_id from travel.travel_block where trip_id = :id and place_id is not null
"""

SPREAD = [
    *(
        f"""
        update travel.{table} c set space_id = t.space_id
        from travel.travel_trip t
        where t.id = :id and c.trip_id = t.id and c.space_id is distinct from t.space_id
        """
        for table in PARTS_OF_TRIP
    ),
    f"""
    update travel.travel_place p set space_id = t.space_id
    from travel.travel_trip t
    where t.id = :id and t.space_id is not null and p.space_id is null
      and p.id in ({PLACES_OF_TRIP})
    """,
]


async def share_trip(connection: AsyncConnection, trip_id: str, space_id: str | None) -> Trip:
    found = (
        await connection.execute(
            text(
                f"select space_id::text as space_id, user_id = {ME} as mine "
                "from travel.travel_trip where id = :id"
            ),
            {"id": trip_id},
        )
    ).one_or_none()
    if found is None:
        raise NotFound(f"viaje {trip_id}")
    if not found.mine:
        raise Conflict("solo quien creó el viaje lo comparte o deja de compartirlo", "NOT_OWNER")
    if found.space_id == space_id:
        return await trip(connection, trip_id)
    if found.space_id is not None:
        await _take_back(connection, trip_id, found.space_id)
    await connection.execute(
        text("update travel.travel_trip set space_id = cast(:space as uuid) where id = :id"),
        {"id": trip_id, "space": space_id},
    )
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def _take_back(connection: AsyncConnection, trip_id: str, space_id: str) -> None:
    for table in PARTS_OF_TRIP:
        await connection.execute(
            text(f"update travel.{table} set space_id = null, user_id = {ME} where trip_id = :id"),
            {"id": trip_id},
        )
    foreign = (
        await connection.execute(
            text(f"""
                select {PLACE_COLUMNS}, osm_type, osm_id from travel.travel_place
                where id in ({PLACES_OF_TRIP}) and user_id <> {ME}
            """),
            {"id": trip_id},
        )
    ).all()
    for row in foreign:
        mine = await save_place(
            connection,
            PlaceIn(
                name=row.name,
                display_name=row.display_name,
                lat=row.lat,
                lon=row.lon,
                country_code=row.country_code,
                region_code=row.region_code,
                kind=row.kind,
                osm_type=row.osm_type,
                osm_id=row.osm_id,
                category=row.category,
            ),
        )
        for statement in (
            "update travel.travel_stay set place_id = :new where trip_id = :id and place_id = :old",
            "update travel.travel_visit set place_id = :new "
            "where trip_id = :id and place_id = :old",
            "update travel.travel_leg set from_place_id = :new "
            "where trip_id = :id and from_place_id = :old",
            "update travel.travel_leg set to_place_id = :new "
            "where trip_id = :id and to_place_id = :old",
            "update travel.travel_block set place_id = :new "
            "where trip_id = :id and place_id = :old",
        ):
            await connection.execute(
                text(statement), {"id": trip_id, "old": row.id, "new": mine.id}
            )
    await connection.execute(
        text(f"""
            update travel.travel_place p set space_id = null
            where p.user_id = {ME} and p.space_id = cast(:space as uuid)
              and not exists (select 1 from travel.travel_stay s
                              where s.place_id = p.id and s.space_id = p.space_id)
              and not exists (select 1 from travel.travel_visit v
                              where v.place_id = p.id and v.space_id = p.space_id)
              and not exists (select 1 from travel.travel_leg l
                              where p.id in (l.from_place_id, l.to_place_id)
                                and l.space_id = p.space_id)
              and not exists (select 1 from travel.travel_block b
                              where b.place_id = p.id and b.space_id = p.space_id)
        """),
        {"space": space_id},
    )


def _agenda(trip_id: str, title: str, starts_on: date, ends_on: date, cancelled: bool = False):
    return dated(
        uid=uid("travel", "trip", trip_id),
        title=title,
        start=starts_on,
        end=ends_on + timedelta(days=1),
        all_day=True,
        tz="Europe/Madrid",
        status="cancelled" if cancelled else "confirmed",
        href=f"/travel/viajes/{trip_id}",
    )


LAST_OF = text("""
    select id, payload from travel.travel_outbox
    where type = :type and payload->>cast(:key as text) = :id
    order by id desc limit 1
""")


async def _last_of(
    connection: AsyncConnection, part_id: str, kind: str = "trip"
) -> tuple[int, dict] | None:
    row = (
        await connection.execute(
            LAST_OF, {"type": f"travel.{kind}", "key": f"{kind}_id", "id": part_id}
        )
    ).one_or_none()
    if row is None:
        return None
    payload = json.loads(row.payload) if isinstance(row.payload, str) else row.payload
    return row.id, payload


async def _enqueue(
    connection: AsyncConnection, part_id: str, payload: dict, kind: str = "trip"
) -> None:
    last = await _last_of(connection, part_id, kind)
    if last is not None and last[1] == payload:
        return
    said = json.dumps(payload, sort_keys=True)
    previous = last[0] if last else 0
    digest = hashlib.sha256(f"{previous}\n{said}".encode()).hexdigest()[:16]
    await connection.execute(
        text("""
            insert into travel.travel_outbox (type, payload, dedup_hash)
            values (:type, cast(:payload as jsonb), :hash)
            on conflict (user_id, dedup_hash) do nothing
        """),
        {"type": f"travel.{kind}", "payload": said, "hash": f"{kind}:{part_id}:{digest}"},
    )


def _leg_agenda(trip_id: str, leg: Leg) -> dict:
    from travel import bookings, zones

    named = " ".join(part for part in (leg.carrier, leg.number) if part)
    title = " ".join(part for part in (bookings.TICKETS[leg.mode], named) if part)
    origin = leg.from_place
    where = f"{origin.name} ({leg.from_code})" if leg.from_code else origin.name
    if leg.terminal:
        where = f"{where} · terminal {leg.terminal}"
    leaves = zones.zone_of(origin.country_code, origin.lat, origin.lon)
    common = {
        "uid": uid("travel", "leg", leg.id),
        "title": f"{title} · {origin.name} → {leg.to_place.name}",
        "tz": leaves,
        "location": where[:300],
        "status": "confirmed",
        "href": f"/travel/viajes/{trip_id}/dias/{leg.travelled_on.isoformat()}",
    }
    if leg.departs_at is None:
        return dated(
            start=leg.travelled_on,
            end=leg.travelled_on + timedelta(days=1),
            all_day=True,
            **common,
        )
    start = datetime.combine(leg.travelled_on, leg.departs_at, ZoneInfo(leaves))
    end = start
    if leg.arrives_at is not None:
        target = leg.to_place
        arrives = ZoneInfo(zones.zone_of(target.country_code, target.lat, target.lon))
        end = datetime.combine(leg.arrives_on or leg.travelled_on, leg.arrives_at, arrives)
        if end < start and leg.arrives_on is None:
            end += timedelta(days=1)
        end = max(end, start)
    return dated(start=start.isoformat(), end=end.isoformat(), all_day=False, **common)


LEGS_OUT = text("""
    select leg_id, payload from (
        select distinct on (payload->>'leg_id') payload->>'leg_id' as leg_id, payload
        from travel.travel_outbox
        where type = 'travel.leg' and payload->>'trip_id' = :trip
        order by payload->>'leg_id', id desc
    ) last
    where not (payload ? 'removed')
""")


LEG_LAYER = "Trayectos"


async def _sync_legs(connection: AsyncConnection, trip_id: str, legs: list[Leg]) -> None:
    dated_legs = [leg for leg in legs if leg.travelled_on is not None]
    for leg in dated_legs:
        await _enqueue(
            connection,
            leg.id,
            {
                "leg_id": leg.id,
                "trip_id": trip_id,
                "mode": leg.mode,
                "layer": LEG_LAYER,
                KEY: _leg_agenda(trip_id, leg),
            },
            kind="leg",
        )
    kept = {leg.id for leg in dated_legs}
    for row in (await connection.execute(LEGS_OUT, {"trip": trip_id})).all():
        if row.leg_id in kept:
            continue
        payload = json.loads(row.payload) if isinstance(row.payload, str) else row.payload
        await _enqueue(
            connection,
            row.leg_id,
            {
                "leg_id": row.leg_id,
                "trip_id": trip_id,
                "removed": True,
                "layer": LEG_LAYER,
                KEY: {**payload[KEY], "status": "cancelled"},
            },
            kind="leg",
        )


BLOCK_LAYER = "Plan"

BLOCKS_OUT = text("""
    select block_id, payload from (
        select distinct on (payload->>'block_id') payload->>'block_id' as block_id, payload
        from travel.travel_outbox
        where type = 'travel.block' and payload->>'trip_id' = :trip
        order by payload->>'block_id', id desc
    ) last
    where not (payload ? 'removed')
""")


def _block_agenda(trip_id: str, block, zone: str) -> dict:
    start = datetime.combine(block.day, block.starts_at, ZoneInfo(zone))
    end = start
    if block.ends_at is not None:
        end = max(start, datetime.combine(block.day, block.ends_at, ZoneInfo(zone)))
    location = block.place.name if block.place else None
    if block.confirmation:
        location = " · ".join(part for part in (location, f"reserva {block.confirmation}") if part)
    return dated(
        uid=uid("travel", "block", block.id),
        title=block.title,
        start=start.isoformat(),
        end=end.isoformat(),
        all_day=False,
        tz=zone,
        location=(location or "")[:300] or None,
        status="confirmed",
        href=f"/travel/viajes/{trip_id}/dias",
    )


async def _sync_blocks(connection: AsyncConnection, found: Trip | None, trip_id: str) -> None:
    from travel import itinerary, zones

    timed = []
    if found is not None:
        for block in await itinerary.blocks(connection, trip_id):
            if block.day is None or block.starts_at is None:
                continue
            place = block.place
            if place is None or place.lat is None:
                sleeping = next(
                    (s for s in found.stays if s.arrives_on <= block.day <= s.leaves_on), None
                )
                place = sleeping.place if sleeping else None
            zone = (
                zones.zone_of(place.country_code, place.lat, place.lon)
                if place is not None
                else "Europe/Madrid"
            )
            timed.append((block, zone))
    for block, zone in timed:
        await _enqueue(
            connection,
            block.id,
            {
                "block_id": block.id,
                "trip_id": trip_id,
                "kind": block.kind,
                "layer": BLOCK_LAYER,
                KEY: _block_agenda(trip_id, block, zone),
            },
            kind="block",
        )
    kept = {block.id for block, _ in timed}
    for row in (await connection.execute(BLOCKS_OUT, {"trip": trip_id})).all():
        if row.block_id in kept:
            continue
        payload = json.loads(row.payload) if isinstance(row.payload, str) else row.payload
        await _enqueue(
            connection,
            row.block_id,
            {
                "block_id": row.block_id,
                "trip_id": trip_id,
                "removed": True,
                "layer": BLOCK_LAYER,
                KEY: {**payload[KEY], "status": "cancelled"},
            },
            kind="block",
        )


async def _withdraw(
    connection: AsyncConnection, trip_id: str, title: str, starts_on: date, ends_on: date
) -> None:
    last = await _last_of(connection, trip_id)
    if last is None or last[1].get("removed"):
        return
    await _enqueue(
        connection,
        trip_id,
        {
            "trip_id": trip_id,
            "removed": True,
            KEY: _agenda(trip_id, title, starts_on, ends_on, cancelled=True),
        },
    )


async def enqueue(connection: AsyncConnection, found: Trip) -> None:
    if found.status == "plan":
        await _withdraw(connection, found.id, found.title, found.starts_on, found.ends_on)
        await _sync_legs(connection, found.id, [])
        await _sync_blocks(connection, None, found.id)
        return
    await _enqueue(
        connection,
        found.id,
        {
            "trip_id": found.id,
            "title": found.title,
            "starts_on": found.starts_on.isoformat(),
            "ends_on": found.ends_on.isoformat(),
            "nights": found.nights,
            "travellers": found.travellers,
            "countries": found.countries,
            "km": found.km,
            "spend_per_person_eur": found.spend.per_person,
            KEY: _agenda(found.id, found.title, found.starts_on, found.ends_on),
        },
    )
    await _sync_legs(connection, found.id, found.legs)
    await _sync_blocks(connection, found, found.id)


EVERY_TRIP = text("select id::text as id from travel.travel_trip")


async def backfill(connection: AsyncConnection) -> int:
    ids = (await connection.execute(EVERY_TRIP)).scalars().all()
    for trip_id in ids:
        await enqueue(connection, await trip(connection, trip_id))
    return len(ids)


SHARED_TRIPS = text("select id::text as id from travel.travel_trip where space_id is not null")

LAST_PUBLISHED = text("""
    select distinct on (payload->>'trip_id')
           payload->>'trip_id' as trip_id, payload ? 'removed' as removed,
           payload->>'title' as title, payload->>'starts_on' as starts_on,
           payload->>'ends_on' as ends_on
    from travel.travel_outbox
    where type = 'travel.trip'
    order by payload->>'trip_id', id desc
""")


async def sync_shared(connection: AsyncConnection) -> int:
    every = await connection.execute(text("select id::text from travel.travel_trip"))
    visible = set(every.scalars())
    shared = (await connection.execute(SHARED_TRIPS)).scalars().all()
    for trip_id in shared:
        await enqueue(connection, await trip(connection, trip_id))
    gone = 0
    for row in (await connection.execute(LAST_PUBLISHED)).all():
        if row.removed or row.trip_id in visible or not row.title:
            continue
        await _withdraw(
            connection,
            row.trip_id,
            row.title,
            date.fromisoformat(row.starts_on),
            date.fromisoformat(row.ends_on),
        )
        await _sync_legs(connection, row.trip_id, [])
        gone += 1
    return len(shared) + gone
