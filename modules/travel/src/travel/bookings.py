from __future__ import annotations

from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import travel

Kind = Literal["stay", "leg", "block"]

BOOKING = ("confirmation", "provider", "booking_url")
FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "stay": ("travel_stay", (*BOOKING, "check_in_at", "check_out_at", "address")),
    "leg": (
        "travel_leg",
        (
            *BOOKING,
            "departs_at",
            "arrives_on",
            "arrives_at",
            "carrier",
            "number",
            "from_code",
            "to_code",
            "terminal",
            "seat",
            "ticket_leg_id",
        ),
    ),
    "block": ("travel_block", BOOKING),
}

TICKETS = {"plane": "Vuelo", "train": "Tren", "car": "Coche", "bus": "Bus", "boat": "Ferry"}


def _tidy(value):
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    return value


async def save(
    connection: AsyncConnection, trip_id: str, kind: str, part_id: str, request: travel.BookingIn
) -> None:
    table, fields = FIELDS[kind]
    given = [name for name in fields if name in request.model_fields_set]
    if "ticket_leg_id" in given:
        await _check_ticket(connection, trip_id, part_id, getattr(request, "ticket_leg_id", None))
    if given:
        await connection.execute(
            text(
                f"update travel.{table} set "
                + ", ".join(f"{name} = :{name}" for name in given)
                + " where id = :id"
            ),
            {"id": part_id, **{name: _tidy(getattr(request, name)) for name in given}},
        )
    if "cost_eur" in request.model_fields_set:
        await _cost(connection, trip_id, kind, part_id, request.cost_eur)
    if "paid_by" in request.model_fields_set:
        await _payer(connection, trip_id, kind, part_id, request.paid_by)


async def _check_ticket(
    connection: AsyncConnection, trip_id: str, leg_id: str, ticket_leg_id: str | None
) -> None:
    if ticket_leg_id is None:
        return
    if ticket_leg_id == leg_id:
        raise travel.Conflict("un trayecto no va en su propio billete", "INVALID")
    other = (
        await connection.execute(
            text("""
                select trip_id::text as trip_id, ticket_leg_id::text as ticket_leg_id
                from travel.travel_leg where id = cast(:id as uuid)
            """),
            {"id": ticket_leg_id},
        )
    ).one_or_none()
    if other is None or other.trip_id != trip_id:
        raise travel.NotFound(f"trayecto {ticket_leg_id}")
    if other.ticket_leg_id is not None:
        raise travel.Conflict(
            "ese trayecto ya va en el billete de otro: apunta al que lleva el billete",
            "INVALID",
            [{"leg_id": other.ticket_leg_id}],
        )
    riders = await connection.scalar(
        text("select count(*) from travel.travel_leg where ticket_leg_id = cast(:id as uuid)"),
        {"id": leg_id},
    )
    if riders:
        raise travel.Conflict(
            "este trayecto lleva el billete de otros: no puede ir en el de otro", "INVALID"
        )


async def _payer(
    connection: AsyncConnection, trip_id: str, kind: str, part_id: str, who: str | None
) -> None:
    from travel import money

    expense = await connection.scalar(
        text(f"select id::text from travel.travel_expense where {kind}_id = :id"),
        {"id": part_id},
    )
    if expense is None:
        if who is None:
            return
        raise travel.Conflict("quién pagó va con lo que costó: falta cost_eur", "INVALID")
    payer = await money.resolve_traveller(connection, trip_id, who) if who else None
    await connection.execute(
        text("update travel.travel_expense set paid_by = cast(:who as uuid) where id = :id"),
        {"id": expense, "who": payer},
    )


async def _what(connection: AsyncConnection, kind: str, part_id: str) -> tuple[str, str]:
    if kind == "stay":
        row = (
            await connection.execute(
                text("""
                    select s.accommodation, s.provider, p.name
                    from travel.travel_stay s join travel.travel_place p on p.id = s.place_id
                    where s.id = :id
                """),
                {"id": part_id},
            )
        ).one()
        return "lodging", (row.accommodation or row.provider or f"Alojamiento en {row.name}")
    if kind == "leg":
        row = (
            await connection.execute(
                text("""
                    select l.mode, l.carrier, l.number, a.name as a, b.name as b
                    from travel.travel_leg l
                    join travel.travel_place a on a.id = l.from_place_id
                    join travel.travel_place b on b.id = l.to_place_id
                    where l.id = :id
                """),
                {"id": part_id},
            )
        ).one()
        named = " ".join(part for part in (row.carrier, row.number) if part)
        return "transport", f"{TICKETS[row.mode]} {named or f'{row.a} → {row.b}'}"
    row = (
        await connection.execute(
            text("select kind, title from travel.travel_block where id = :id"), {"id": part_id}
        )
    ).one()
    return ("transport" if row.kind == "transport" else "other"), row.title


async def _cost(
    connection: AsyncConnection, trip_id: str, kind: str, part_id: str, cost: Decimal | None
) -> None:
    column = f"{kind}_id"
    existing = await connection.scalar(
        text(f"select id::text from travel.travel_expense where {column} = :id"), {"id": part_id}
    )
    if cost is None:
        if existing:
            await connection.execute(
                text("delete from travel.travel_expense where id = :id"), {"id": existing}
            )
        return
    travellers = await connection.scalar(
        text("select travellers from travel.travel_trip where id = :id"), {"id": trip_id}
    )
    per_person = (Decimal(cost) / travellers).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if existing:
        await connection.execute(
            text("""
                update travel.travel_expense
                set amount_eur = :amount, amount = :total, currency = 'EUR', fx_rate = 1,
                    total_eur = :total
                where id = :id
            """),
            {"id": existing, "amount": per_person, "total": Decimal(cost)},
        )
        return
    category, concept = await _what(connection, kind, part_id)
    await connection.execute(
        text(f"""
            insert into travel.travel_expense
                (trip_id, category, concept, amount_eur, source, {column}, amount, currency,
                 fx_rate, total_eur)
            values (:trip, :category, :concept, :amount, 'app', :part, :total, 'EUR', 1, :total)
        """),
        {
            "trip": trip_id,
            "category": category,
            "concept": concept[:60],
            "amount": per_person,
            "part": part_id,
            "total": Decimal(cost),
        },
    )


class Booking(BaseModel):
    type: Kind
    id: str
    title: str
    detail: str | None
    day: date | None
    until: date | None
    at: time | None
    confirmation: str | None
    provider: str | None
    booking_url: str | None
    cost_eur: float | None
    booked: bool
    paid_by: str | None = None
    ticket_leg_id: str | None = None
    ticket_of: str | None = None


def _booked(*values) -> bool:
    return any(value is not None for value in values)


async def bookings(connection: AsyncConnection, trip_id: str) -> list[Booking]:
    from travel import itinerary

    found = await travel.trip(connection, trip_id)
    listed: list[Booking] = []
    for stay in found.stays:
        listed.append(
            Booking(
                type="stay",
                id=stay.id,
                title=stay.accommodation or stay.place.name,
                detail=" · ".join(
                    part
                    for part in (
                        stay.place.name if stay.accommodation else None,
                        stay.address,
                        f"{stay.nights} noche{'s' if stay.nights != 1 else ''}",
                    )
                    if part
                ),
                day=stay.arrives_on,
                until=stay.leaves_on,
                at=stay.check_in_at,
                confirmation=stay.confirmation,
                provider=stay.provider,
                booking_url=stay.booking_url,
                cost_eur=stay.cost_eur,
                booked=_booked(stay.confirmation, stay.provider, stay.booking_url, stay.cost_eur),
                paid_by=stay.paid_by,
            )
        )
    by_id = {leg.id: leg for leg in found.legs}
    for leg in found.legs:
        route = f"{leg.from_place.name} → {leg.to_place.name}"
        ticket = by_id.get(leg.ticket_leg_id) if leg.ticket_leg_id else None
        source = ticket or leg
        listed.append(
            Booking(
                type="leg",
                id=leg.id,
                title=route,
                detail=" · ".join(
                    part
                    for part in (
                        TICKETS[leg.mode],
                        " ".join(p for p in (leg.carrier, leg.number) if p) or None,
                        f"terminal {leg.terminal}" if leg.terminal else None,
                        f"asiento {leg.seat}" if leg.seat else None,
                    )
                    if part
                ),
                day=leg.travelled_on,
                until=leg.arrives_on,
                at=leg.departs_at,
                confirmation=source.confirmation,
                provider=source.provider,
                booking_url=source.booking_url,
                cost_eur=leg.cost_eur,
                booked=_booked(
                    source.confirmation, source.provider, source.booking_url, source.cost_eur
                ),
                paid_by=leg.paid_by,
                ticket_leg_id=ticket.id if ticket else None,
                ticket_of=f"{ticket.from_place.name} → {ticket.to_place.name}" if ticket else None,
            )
        )
    for block in await itinerary.blocks(connection, trip_id):
        if not _booked(block.confirmation, block.provider, block.booking_url, block.cost_eur):
            continue
        listed.append(
            Booking(
                type="block",
                id=block.id,
                title=block.title,
                detail=block.place.name if block.place else None,
                day=block.day,
                until=None,
                at=block.starts_at,
                confirmation=block.confirmation,
                provider=block.provider,
                booking_url=block.booking_url,
                cost_eur=block.cost_eur,
                booked=True,
                paid_by=block.paid_by,
            )
        )
    return sorted(
        listed,
        key=lambda one: (one.day or date.max, one.at or time.max, one.type != "leg", one.title),
    )
