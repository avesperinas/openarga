from __future__ import annotations

from datetime import date
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import geo
from travel.travel.common import Conflict, NotFound, Source, today
from travel.travel.models import BookingIn, ExpenseIn, Leg, LegIn, StayIn, Trip, Visit, VisitIn
from travel.travel.places import Place, PlaceIn, place_by_id, set_category
from travel.travel.read import trip
from travel.travel.sync import _touch


async def _check_dates(connection: AsyncConnection, trip_id: str, *days: date | None) -> None:
    span = (
        await connection.execute(
            text("select starts_on, ends_on from travel.travel_trip where id = :id"),
            {"id": trip_id},
        )
    ).one_or_none()
    if span is None:
        raise NotFound(f"viaje {trip_id}")
    outside = [day for day in days if day is not None and not span.starts_on <= day <= span.ends_on]
    if outside:
        raise Conflict(
            f"{outside[0].isoformat()} está fuera del viaje "
            f"({span.starts_on.isoformat()} a {span.ends_on.isoformat()})",
            "DATE_OUT_OF_RANGE",
            [
                {
                    "date": day.isoformat(),
                    "trip_starts_on": span.starts_on.isoformat(),
                    "trip_ends_on": span.ends_on.isoformat(),
                }
                for day in outside
            ],
        )


async def _check_overlap(
    connection: AsyncConnection,
    trip_id: str,
    arrives_on: date,
    leaves_on: date,
    stay_id: str | None = None,
) -> None:
    rows = (
        await connection.execute(
            text("""
                select s.id::text as id, p.name, s.arrives_on, s.leaves_on
                from travel.travel_stay s join travel.travel_place p on p.id = s.place_id
                where s.trip_id = :trip
                  and (cast(:stay as uuid) is null or s.id <> cast(:stay as uuid))
                  and s.arrives_on < :leaves and :arrives < s.leaves_on
                order by s.arrives_on
            """),
            {"trip": trip_id, "stay": stay_id, "arrives": arrives_on, "leaves": leaves_on},
        )
    ).all()
    if rows:
        raise Conflict(
            f"esas noches ya son de {rows[0].name}: dos lugares principales no comparten noche",
            "STAY_OVERLAP",
            [
                {
                    "stay_id": row.id,
                    "name": row.name,
                    "arrives_on": row.arrives_on.isoformat(),
                    "leaves_on": row.leaves_on.isoformat(),
                }
                for row in rows
            ],
        )


async def add_stay(connection: AsyncConnection, trip_id: str, request: StayIn) -> Trip:
    await _check_dates(connection, trip_id, request.arrives_on, request.leaves_on)
    await _check_overlap(connection, trip_id, request.arrives_on, request.leaves_on)
    await place_by_id(connection, request.place_id)
    stay_id = await connection.scalar(
        text("""
            insert into travel.travel_stay (trip_id, place_id, arrives_on, leaves_on, accommodation)
            values (:trip, :place, :arrives, :leaves, :accommodation)
            returning id::text
        """),
        {
            "trip": trip_id,
            "place": request.place_id,
            "arrives": request.arrives_on,
            "leaves": request.leaves_on,
            "accommodation": request.accommodation,
        },
    )
    await _booked(connection, trip_id, "stay", stay_id, request)
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def _booked(
    connection: AsyncConnection, trip_id: str, kind: str, part_id: str, request: BookingIn
) -> None:
    from travel import bookings

    await bookings.save(connection, trip_id, kind, part_id, request)


async def _refresh_km(connection: AsyncConnection, leg_ids: list[str]) -> None:
    if not leg_ids:
        return
    rows = (
        await connection.execute(
            text("""
                select l.id::text as id, l.mode, a.lat as a_lat, a.lon as a_lon,
                       b.lat as b_lat, b.lon as b_lon
                from travel.travel_leg l
                join travel.travel_place a on a.id = l.from_place_id
                join travel.travel_place b on b.id = l.to_place_id
                where l.id::text = any(:ids)
            """),
            {"ids": leg_ids},
        )
    ).all()
    for row in rows:
        await connection.execute(
            text("update travel.travel_leg set km = :km where id = :id"),
            {
                "id": row.id,
                "km": geo.leg_km(row.mode, (row.a_lat, row.a_lon), (row.b_lat, row.b_lon)),
            },
        )


async def update_stay(
    connection: AsyncConnection, trip_id: str, stay_id: str, request: StayIn
) -> Trip:
    await _check_dates(connection, trip_id, request.arrives_on, request.leaves_on)
    before = await trip(connection, trip_id)
    old = next((one for one in before.stays if one.id == stay_id), None)
    if old is None:
        raise NotFound(f"lugar principal {stay_id}")
    await _check_overlap(connection, trip_id, request.arrives_on, request.leaves_on, stay_id)
    await place_by_id(connection, request.place_id)
    await connection.execute(
        text("""
            update travel.travel_stay
            set place_id = :place, arrives_on = :arrives, leaves_on = :leaves,
                accommodation = :accommodation
            where id = :id and trip_id = :trip
        """),
        {
            "id": stay_id,
            "trip": trip_id,
            "place": request.place_id,
            "arrives": request.arrives_on,
            "leaves": request.leaves_on,
            "accommodation": request.accommodation,
        },
    )
    await _booked(connection, trip_id, "stay", stay_id, request)
    if old.place.id != request.place_id:
        moved = []
        for leg in before.legs:
            start = request.place_id if leg.from_stay_id == stay_id else leg.from_place.id
            end = request.place_id if leg.to_stay_id == stay_id else leg.to_place.id
            if (start, end) == (leg.from_place.id, leg.to_place.id):
                continue
            if start == end:
                raise Conflict(
                    "un trayecto quedaría yendo de un sitio al mismo",
                    "INVALID",
                    [{"kind": "leg", "leg_id": leg.id}],
                )
            await connection.execute(
                text(
                    "update travel.travel_leg set from_place_id = :start, to_place_id = :end "
                    "where id = :id"
                ),
                {"id": leg.id, "start": start, "end": end},
            )
            moved.append(leg.id)
        await _refresh_km(connection, moved)
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def stay_covering(connection: AsyncConnection, trip_id: str, day: date | None) -> str | None:
    if day is None:
        return None
    return await connection.scalar(
        text("""
            select id::text from travel.travel_stay
            where trip_id = :trip and arrives_on <= :day and leaves_on >= :day
            order by arrives_on desc limit 1
        """),
        {"trip": trip_id, "day": day},
    )


async def _check_stay_of(connection: AsyncConnection, trip_id: str, stay_id: str | None) -> None:
    if stay_id is None:
        return
    belongs = await connection.scalar(
        text("select 1 from travel.travel_stay where id = :id and trip_id = :trip"),
        {"id": stay_id, "trip": trip_id},
    )
    if not belongs:
        raise Conflict(
            "ese lugar principal no es de este viaje", "NOT_FOUND", [{"stay_id": stay_id}]
        )


async def add_visit(connection: AsyncConnection, trip_id: str, request: VisitIn) -> Trip:
    await _check_dates(connection, trip_id, request.visited_on)
    await place_by_id(connection, request.place_id)
    await _check_stay_of(connection, trip_id, request.stay_id)
    from travel import itinerary

    if await itinerary._same_visit(connection, trip_id, request.visited_on, request.place_id):
        return await trip(connection, trip_id)
    await connection.execute(
        text("""
            insert into travel.travel_visit (trip_id, place_id, stay_id, visited_on, note)
            values (:trip, :place, :stay, :day, :note)
        """),
        {
            "trip": trip_id,
            "place": request.place_id,
            "stay": request.stay_id,
            "day": request.visited_on,
            "note": request.note,
        },
    )
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def update_visit(
    connection: AsyncConnection, trip_id: str, visit_id: str, request: VisitIn
) -> Trip:
    await _check_dates(connection, trip_id, request.visited_on)
    await place_by_id(connection, request.place_id)
    await _check_stay_of(connection, trip_id, request.stay_id)
    updated = await connection.execute(
        text("""
            update travel.travel_visit
            set place_id = :place, stay_id = :stay, visited_on = :day, note = :note
            where id = :id and trip_id = :trip
        """),
        {
            "id": visit_id,
            "trip": trip_id,
            "place": request.place_id,
            "stay": request.stay_id,
            "day": request.visited_on,
            "note": request.note,
        },
    )
    if updated.rowcount == 0:
        raise NotFound(f"visita {visit_id}")
    await connection.execute(
        text("""
            update travel.travel_block
            set place_id = :place,
                position = case when day is distinct from :day then 1000000 else position end,
                day = :day
            where visit_id = :id
        """),
        {"id": visit_id, "place": request.place_id, "day": request.visited_on},
    )
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def add_leg(connection: AsyncConnection, trip_id: str, request: LegIn) -> Trip:
    await _check_dates(connection, trip_id, request.travelled_on, request.arrives_on)
    start = await place_by_id(connection, request.from_place_id)
    end = await place_by_id(connection, request.to_place_id)
    leg_id = await connection.scalar(
        text("""
            insert into travel.travel_leg
                (trip_id, from_place_id, to_place_id, travelled_on, mode, km, note, on_map)
            values (:trip, :start, :end, :day, :mode, :km, :note, :on_map)
            returning id::text
        """),
        {
            "trip": trip_id,
            "start": start.id,
            "end": end.id,
            "day": request.travelled_on,
            "mode": request.mode,
            "km": geo.leg_km(request.mode, (start.lat, start.lon), (end.lat, end.lon)),
            "note": request.note,
            "on_map": request.on_map,
        },
    )
    await _booked(connection, trip_id, "leg", leg_id, request)
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def update_leg(
    connection: AsyncConnection, trip_id: str, leg_id: str, request: LegIn
) -> Trip:
    await _check_dates(connection, trip_id, request.travelled_on, request.arrives_on)
    start = await place_by_id(connection, request.from_place_id)
    end = await place_by_id(connection, request.to_place_id)
    updated = await connection.execute(
        text("""
            update travel.travel_leg
            set from_place_id = :start, to_place_id = :end, travelled_on = :day, mode = :mode,
                km = :km, note = :note, on_map = :on_map
            where id = :id and trip_id = :trip
        """),
        {
            "id": leg_id,
            "trip": trip_id,
            "start": start.id,
            "end": end.id,
            "day": request.travelled_on,
            "mode": request.mode,
            "km": geo.leg_km(request.mode, (start.lat, start.lon), (end.lat, end.lon)),
            "note": request.note,
            "on_map": request.on_map,
        },
    )
    if updated.rowcount == 0:
        raise NotFound(f"trayecto {leg_id}")
    await _booked(connection, trip_id, "leg", leg_id, request)
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def record_expense(
    connection: AsyncConnection, trip_id: str, request: ExpenseIn, source: Source = "app"
) -> tuple[str, Trip]:
    exists = await connection.scalar(
        text("select 1 from travel.travel_trip where id = :id"), {"id": trip_id}
    )
    if not exists:
        raise NotFound(f"viaje {trip_id}")
    if request.id is not None:
        already = await connection.scalar(
            text("select id::text from travel.travel_expense where id = :id"), {"id": request.id}
        )
        if already:
            return already, await trip(connection, trip_id)
    money = await _money(connection, trip_id, request)
    expense_id = await connection.scalar(
        text("""
            insert into travel.travel_expense
                (id, trip_id, category, concept, amount_eur, note, source, amount, currency,
                 fx_rate, fx_on, total_eur, spent_on, paid_by)
            values (coalesce(cast(:expense as uuid), gen_random_uuid()), :trip, :category,
                    :concept, :amount_eur, :note, :source, :amount, :currency, :fx_rate, :fx_on,
                    :total_eur, :spent_on, cast(:paid_by as uuid))
            returning id::text
        """),
        {
            "expense": str(request.id) if request.id else None,
            "trip": trip_id,
            "category": request.category,
            "concept": request.concept,
            "note": request.note,
            "source": source,
            **money,
        },
    )
    from travel import money as split

    await split.save_shares(connection, trip_id, expense_id, request)
    await _touch(connection, trip_id)
    return expense_id, await trip(connection, trip_id)


async def _money(connection: AsyncConnection, trip_id: str, request: ExpenseIn) -> dict:
    from travel import money

    empty = {
        "amount": None,
        "currency": None,
        "fx_rate": None,
        "fx_on": None,
        "total_eur": None,
        "spent_on": request.spent_on,
        "paid_by": None,
    }
    if request.amount is None:
        return {**empty, "amount_eur": request.amount_eur}
    travellers = await connection.scalar(
        text("select travellers from travel.travel_trip where id = :id"), {"id": trip_id}
    )
    if request.paid_by is not None:
        belongs = await connection.scalar(
            text("select 1 from travel.travel_traveller where id = :id and trip_id = :trip"),
            {"id": request.paid_by, "trip": trip_id},
        )
        if not belongs:
            raise Conflict("quien pagó no es viajero de este viaje", "NOT_FOUND")
    day = request.spent_on or today()
    done = await money.convert(request.amount, request.currency or "EUR", day, request.fx_rate)
    return {
        "amount": done.amount,
        "currency": done.currency,
        "fx_rate": done.fx_rate,
        "fx_on": done.fx_on,
        "total_eur": done.total_eur,
        "spent_on": day,
        "paid_by": request.paid_by,
        "amount_eur": money.per_person(done.total_eur, travellers),
    }


async def add_expense(
    connection: AsyncConnection, trip_id: str, request: ExpenseIn, source: Source = "app"
) -> Trip:
    return (await record_expense(connection, trip_id, request, source))[1]


async def update_expense(
    connection: AsyncConnection, trip_id: str, expense_id: str, request: ExpenseIn
) -> Trip:
    exists = await connection.scalar(
        text("select 1 from travel.travel_expense where id = :id and trip_id = :trip"),
        {"id": expense_id, "trip": trip_id},
    )
    if not exists:
        raise NotFound(f"gasto {expense_id}")
    money = await _money(connection, trip_id, request)
    updated = await connection.execute(
        text("""
            update travel.travel_expense
            set category = :category, concept = :concept, amount_eur = :amount_eur, note = :note,
                amount = :amount, currency = :currency, fx_rate = :fx_rate, fx_on = :fx_on,
                total_eur = :total_eur, spent_on = :spent_on, paid_by = cast(:paid_by as uuid)
            where id = :id and trip_id = :trip
        """),
        {
            "id": expense_id,
            "trip": trip_id,
            "category": request.category,
            "concept": request.concept,
            "note": request.note,
            **money,
        },
    )
    if updated.rowcount == 0:
        raise NotFound(f"gasto {expense_id}")
    from travel import money as split

    await split.save_shares(connection, trip_id, expense_id, request)
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


PARTS = {
    "stays": "travel.travel_stay",
    "visits": "travel.travel_visit",
    "legs": "travel.travel_leg",
    "expenses": "travel.travel_expense",
}
PART_NAMES = {
    "stays": "lugar principal",
    "visits": "visita",
    "legs": "trayecto",
    "expenses": "gasto",
}


async def trip_of(connection: AsyncConnection, part: str, part_id: str) -> str:
    trip_id = await connection.scalar(
        text(f"select trip_id::text from {PARTS[part]} where id = :id"), {"id": part_id}
    )
    if trip_id is None:
        raise NotFound(f"{PART_NAMES[part]} {part_id}")
    return trip_id


def _visit_ref(visit: Visit) -> dict:
    return {
        "kind": "visit",
        "visit_id": visit.id,
        "name": visit.place.name,
        "visited_on": visit.visited_on.isoformat() if visit.visited_on else None,
    }


def _leg_ref(leg: Leg) -> dict:
    return {
        "kind": "leg",
        "leg_id": leg.id,
        "name": f"{leg.from_place.name} → {leg.to_place.name}",
        "travelled_on": leg.travelled_on.isoformat() if leg.travelled_on else None,
    }


async def stay_dependents(
    connection: AsyncConnection, trip_id: str, stay_id: str
) -> tuple[list[Visit], list[Leg]]:
    found = await trip(connection, trip_id)
    if not any(one.id == stay_id for one in found.stays):
        raise NotFound(f"lugar principal {stay_id}")
    visits = [one for one in found.visits if one.stay_id == stay_id]
    legs = [one for one in found.legs if stay_id in (one.from_stay_id, one.to_stay_id)]
    return visits, legs


OnDependents = Literal["reject", "detach", "delete"]


async def remove_stay(
    connection: AsyncConnection, trip_id: str, stay_id: str, on_dependents: OnDependents
) -> tuple[Trip, dict[str, int]]:
    visits, legs = await stay_dependents(connection, trip_id, stay_id)
    if (visits or legs) and on_dependents == "reject":
        raise Conflict(
            "hay visitas o trayectos que cuelgan de este lugar principal",
            "HAS_DEPENDENTS",
            [*(_visit_ref(one) for one in visits), *(_leg_ref(one) for one in legs)],
        )
    if on_dependents == "delete":
        await connection.execute(
            text("delete from travel.travel_visit where id::text = any(:ids)"),
            {"ids": [one.id for one in visits]},
        )
        await connection.execute(
            text("delete from travel.travel_leg where id::text = any(:ids)"),
            {"ids": [one.id for one in legs]},
        )
    await connection.execute(
        text("delete from travel.travel_stay where id = :id and trip_id = :trip"),
        {"id": stay_id, "trip": trip_id},
    )
    await _touch(connection, trip_id)
    return await trip(connection, trip_id), {"visits": len(visits), "legs": len(legs)}


async def delete_part(connection: AsyncConnection, trip_id: str, part: str, part_id: str) -> Trip:
    table = PARTS.get(part)
    if table is None:
        raise NotFound(part)
    if part == "stays":
        _, legs = await stay_dependents(connection, trip_id, part_id)
        if legs:
            raise Conflict(
                "hay trayectos que llegan o salen de aquí: quítalos antes",
                "HAS_DEPENDENTS",
                [_leg_ref(one) for one in legs],
            )
    deleted = await connection.execute(
        text(f"delete from {table} where id = :id and trip_id = :trip"),
        {"id": part_id, "trip": trip_id},
    )
    if deleted.rowcount == 0:
        raise NotFound(f"{PART_NAMES[part]} {part_id}")
    await _touch(connection, trip_id)
    return await trip(connection, trip_id)


async def trips_using(connection: AsyncConnection, place_id: str) -> list[str]:
    return list(
        (
            await connection.execute(
                text("""
                    select trip_id::text from travel.travel_stay where place_id = :id
                    union
                    select trip_id::text from travel.travel_visit where place_id = :id
                    union
                    select trip_id::text from travel.travel_leg
                    where from_place_id = :id or to_place_id = :id
                    union
                    select trip_id::text from travel.travel_block where place_id = :id
                """),
                {"id": place_id},
            )
        ).scalars()
    )


async def update_place(
    connection: AsyncConnection,
    place_id: str,
    name: str | None = None,
    candidate: PlaceIn | None = None,
    category: str | None = None,
) -> tuple[Place, list[str]]:
    await place_by_id(connection, place_id)
    if category is not None:
        await set_category(connection, place_id, category)
        if name is None and candidate is None:
            affected = await trips_using(connection, place_id)
            for trip_id in affected:
                await _touch(connection, trip_id)
            return await place_by_id(connection, place_id), affected
    new_name = " ".join((name or (candidate.name if candidate else "")).split())
    if not new_name:
        raise Conflict("hace falta un nombre nuevo o un candidato de find_place", "INVALID")
    if candidate is None:
        await connection.execute(
            text("update travel.travel_place set name = :name where id = :id"),
            {"id": place_id, "name": new_name},
        )
    else:
        if candidate.osm_id is not None:
            clash = await connection.scalar(
                text("""
                    select id::text from travel.travel_place
                    where osm_type = :type and osm_id = :osm and id <> :id
                      and user_id = (select user_id from travel.travel_place where id = :id)
                """),
                {"type": candidate.osm_type, "osm": candidate.osm_id, "id": place_id},
            )
            if clash:
                raise Conflict(
                    "ese lugar de OpenStreetMap ya está guardado con otro place_id: usa ese",
                    "DUPLICATE_PLACE",
                    [{"place_id": clash}],
                )
        country, region = geo.locate(
            candidate.lat, candidate.lon, candidate.country_code, candidate.region_code
        )
        await connection.execute(
            text("""
                update travel.travel_place
                set name = :name, display_name = :display, lat = :lat, lon = :lon,
                    country_code = :country, region_code = :region, kind = :kind,
                    osm_type = :osm_type, osm_id = :osm_id
                where id = :id
            """),
            {
                "id": place_id,
                "name": new_name,
                "display": candidate.display_name,
                "lat": candidate.lat,
                "lon": candidate.lon,
                "country": country,
                "region": region,
                "kind": candidate.kind,
                "osm_type": candidate.osm_type,
                "osm_id": candidate.osm_id,
            },
        )
        legs = (
            await connection.execute(
                text(
                    "select id::text from travel.travel_leg "
                    "where from_place_id = :id or to_place_id = :id"
                ),
                {"id": place_id},
            )
        ).scalars()
        await _refresh_km(connection, list(legs))
    affected = await trips_using(connection, place_id)
    for trip_id in affected:
        await _touch(connection, trip_id)
    return await place_by_id(connection, place_id), affected
