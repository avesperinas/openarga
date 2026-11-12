from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel import geo
from travel.travel.common import NotFound, phase_of
from travel.travel.models import Cover, Expense, Leg, Stay, Trip, Visit, days_of, spend_of
from travel.travel.places import Place

TRIP_COLUMNS = (
    "id::text, title, starts_on, ends_on, travellers, companions, tags, notes, source, status, "
    "idea_id::text as idea_id, budget_eur, summary, "
    "(select json_build_object('version', floor(extract(epoch from c.updated_at) * 1000)::bigint,"
    " 'author', c.credit_author, 'license', c.credit_license, 'page', c.credit_page)"
    " from travel.travel_cover c where c.trip_id = travel_trip.id) as cover, "
    f"archived_at is not null as archived, space_id::text as space_id, user_id = {ME} as mine"
)


async def _trip_rows(connection: AsyncConnection, trip_id: str | None = None):
    where = "where id = :id" if trip_id else ""
    return (
        await connection.execute(
            text(
                f"select {TRIP_COLUMNS} from travel.travel_trip {where} "
                "order by starts_on desc, title"
            ),
            {"id": trip_id} if trip_id else {},
        )
    ).all()


def _joined_place(row, prefix: str) -> Place:
    known = geo.names()
    country = getattr(row, f"{prefix}country_code")
    region = getattr(row, f"{prefix}region_code")
    return Place(
        id=getattr(row, f"{prefix}id"),
        name=getattr(row, f"{prefix}name"),
        display_name=getattr(row, f"{prefix}display_name"),
        lat=getattr(row, f"{prefix}lat"),
        lon=getattr(row, f"{prefix}lon"),
        country_code=country,
        region_code=region,
        country=known.get(country) if country else None,
        region=known.get(region) if region else None,
        kind=getattr(row, f"{prefix}kind"),
        category=getattr(row, f"{prefix}category"),
    )


def _place_select(alias: str, prefix: str) -> str:
    return (
        ", ".join(
            f"{alias}.{column} as {prefix}{column}"
            for column in (
                "name",
                "display_name",
                "lat",
                "lon",
                "country_code",
                "region_code",
                "kind",
                "category",
            )
        )
        + f", {alias}.id::text as {prefix}id"
    )


async def _children(connection: AsyncConnection, trip_ids: list[str]):
    ids = {"ids": trip_ids}
    stays = (
        await connection.execute(
            text(f"""
                select s.id::text as id, s.trip_id::text as trip_id, s.arrives_on, s.leaves_on,
                       s.accommodation, s.check_in_at, s.check_out_at, s.address, s.confirmation,
                       s.provider, s.booking_url, {_place_select("p", "p_")}
                from travel.travel_stay s join travel.travel_place p on p.id = s.place_id
                where s.trip_id::text = any(:ids)
                order by s.arrives_on, s.leaves_on, p.name
            """),
            ids,
        )
    ).all()
    visits = (
        await connection.execute(
            text(f"""
                select v.id::text as id, v.trip_id::text as trip_id, v.stay_id::text as stay_id,
                       v.visited_on, v.note, {_place_select("p", "p_")}
                from travel.travel_visit v join travel.travel_place p on p.id = v.place_id
                where v.trip_id::text = any(:ids)
                order by v.visited_on nulls last, p.name
            """),
            ids,
        )
    ).all()
    legs = (
        await connection.execute(
            text(f"""
                select l.id::text as id, l.trip_id::text as trip_id, l.mode, l.travelled_on,
                       l.km, l.note, l.on_map, l.departs_at, l.arrives_on, l.arrives_at, l.carrier,
                       l.number, l.from_code, l.to_code, l.terminal, l.seat, l.confirmation,
                       l.provider, l.booking_url, l.ticket_leg_id::text as ticket_leg_id,
                       {_place_select("a", "a_")}, {_place_select("b", "b_")}
                from travel.travel_leg l
                join travel.travel_place a on a.id = l.from_place_id
                join travel.travel_place b on b.id = l.to_place_id
                where l.trip_id::text = any(:ids)
                order by l.travelled_on nulls last, l.id
            """),
            ids,
        )
    ).all()
    expenses = (
        await connection.execute(
            text(f"""
                select id::text as id, trip_id::text as trip_id, category, concept, amount_eur,
                       note, user_id = {ME} as mine, stay_id::text as stay_id,
                       leg_id::text as leg_id, block_id::text as block_id, amount, currency,
                       fx_rate, fx_on, total_eur, spent_on, paid_by::text as paid_by,
                       (select r.name from travel.travel_traveller r where r.id = paid_by)
                           as paid_by_name
                from travel.travel_expense where trip_id::text = any(:ids)
                order by category, created_at
            """),
            ids,
        )
    ).all()
    return stays, visits, legs, expenses


def _stay_at(stays: list[Stay], place_id: str, day: date | None, end: str) -> str | None:
    matches = [one for one in stays if one.place.id == place_id]
    if len(matches) > 1 and day is not None:
        exact = [s for s in matches if (s.leaves_on if end == "from" else s.arrives_on) == day]
        covering = [s for s in matches if s.arrives_on <= day <= s.leaves_on]
        matches = exact or covering or matches
    return matches[0].id if matches else None


def _expense(e, travellers: int) -> Expense:
    per_person = float(e.amount_eur)
    whole = per_person * travellers
    trusted = e.total_eur is not None and abs(float(e.total_eur) - whole) <= 0.01 * travellers
    return Expense(
        id=e.id,
        category=e.category,
        concept=e.concept,
        amount_eur=per_person,
        note=e.note,
        mine=bool(e.mine),
        stay_id=e.stay_id,
        leg_id=e.leg_id,
        block_id=e.block_id,
        amount=float(e.amount) if trusted and e.amount is not None else round(whole, 2),
        currency=e.currency if trusted and e.currency else "EUR",
        fx_rate=float(e.fx_rate) if trusted and e.fx_rate is not None else None,
        fx_on=e.fx_on if trusted else None,
        total_eur=float(e.total_eur) if trusted else round(whole, 2),
        spent_on=e.spent_on,
        paid_by=e.paid_by if trusted else None,
        paid_by_name=e.paid_by_name if trusted else None,
    )


def _build(row, stays, visits, legs, expenses) -> Trip:
    mine_expenses = [e for e in expenses if e.trip_id == row.id]

    def cost(column: str, part_id: str) -> float | None:
        found = next((e for e in mine_expenses if getattr(e, column) == part_id), None)
        return round(float(found.amount_eur) * row.travellers, 2) if found else None

    def payer(column: str, part_id: str) -> str | None:
        found = next((e for e in mine_expenses if getattr(e, column) == part_id), None)
        return found.paid_by_name if found else None

    trip_stays = [
        Stay(
            id=s.id,
            place=_joined_place(s, "p_"),
            arrives_on=s.arrives_on,
            leaves_on=s.leaves_on,
            nights=(s.leaves_on - s.arrives_on).days,
            accommodation=s.accommodation,
            check_in_at=s.check_in_at,
            check_out_at=s.check_out_at,
            address=s.address,
            confirmation=s.confirmation,
            provider=s.provider,
            booking_url=s.booking_url,
            cost_eur=cost("stay_id", s.id),
            paid_by=payer("stay_id", s.id),
        )
        for s in stays
        if s.trip_id == row.id
    ]
    trip_visits = [
        Visit(
            id=v.id,
            place=_joined_place(v, "p_"),
            stay_id=v.stay_id,
            visited_on=v.visited_on,
            note=v.note,
        )
        for v in visits
        if v.trip_id == row.id
    ]
    trip_legs = [
        Leg(
            id=leg.id,
            from_place=_joined_place(leg, "a_"),
            to_place=_joined_place(leg, "b_"),
            from_stay_id=_stay_at(trip_stays, leg.a_id, leg.travelled_on, "from"),
            to_stay_id=_stay_at(trip_stays, leg.b_id, leg.travelled_on, "to"),
            mode=leg.mode,
            travelled_on=leg.travelled_on,
            km=float(leg.km) if leg.km is not None else None,
            note=leg.note,
            on_map=leg.on_map,
            departs_at=leg.departs_at,
            arrives_on=leg.arrives_on,
            arrives_at=leg.arrives_at,
            carrier=leg.carrier,
            number=leg.number,
            from_code=leg.from_code,
            to_code=leg.to_code,
            terminal=leg.terminal,
            seat=leg.seat,
            confirmation=leg.confirmation,
            provider=leg.provider,
            booking_url=leg.booking_url,
            cost_eur=cost("leg_id", leg.id),
            paid_by=payer("leg_id", leg.id),
            ticket_leg_id=leg.ticket_leg_id,
        )
        for leg in legs
        if leg.trip_id == row.id
    ]
    trip_expenses = [_expense(e, row.travellers) for e in mine_expenses]
    countries: list[str] = []
    for place in [s.place for s in trip_stays] + [v.place for v in trip_visits]:
        if place.country_code and place.country_code not in countries:
            countries.append(place.country_code)
    days = days_of(row.starts_on, row.ends_on)
    return Trip(
        id=row.id,
        title=row.title,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        days=days,
        nights=(row.ends_on - row.starts_on).days,
        travellers=row.travellers,
        companions=list(row.companions),
        tags=list(row.tags),
        notes=row.notes,
        source=row.source,
        archived=row.archived,
        status=row.status,
        phase=phase_of(row.status, row.starts_on, row.ends_on),
        idea_id=row.idea_id,
        budget_eur=float(row.budget_eur) if row.budget_eur is not None else None,
        summary=row.summary,
        cover=Cover(**row.cover) if row.cover else None,
        space_id=row.space_id,
        mine=bool(row.mine),
        countries=countries,
        km=round(sum(leg.km or 0 for leg in trip_legs), 1),
        spend=spend_of(trip_expenses, row.travellers, days),
        stays=trip_stays,
        visits=trip_visits,
        legs=trip_legs,
        expenses=trip_expenses,
    )


async def all_trips(connection: AsyncConnection) -> list[Trip]:
    rows = await _trip_rows(connection)
    if not rows:
        return []
    children = await _children(connection, [row.id for row in rows])
    return [_build(row, *children) for row in rows]


def lived(trips: list[Trip]) -> list[Trip]:
    return [one for one in trips if one.phase in ("ongoing", "done")]


async def trip(connection: AsyncConnection, trip_id: str) -> Trip:
    rows = await _trip_rows(connection, trip_id)
    if not rows:
        raise NotFound(f"viaje {trip_id}")
    return _build(rows[0], *(await _children(connection, [trip_id])))
