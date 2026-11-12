from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from travel import hub, travel

CENT = Decimal("0.01")


class Traveller(BaseModel):
    id: str
    name: str
    me: bool
    position: int
    member_user_id: str | None = None


async def travellers(connection: AsyncConnection, trip_id: str) -> list[Traveller]:
    rows = (
        await connection.execute(
            text(f"""
                select id::text as id, name, position, member_user_id = {ME} as me,
                       member_user_id::text as member_user_id
                from travel.travel_traveller where trip_id = :trip order by position, name
            """),
            {"trip": trip_id},
        )
    ).all()
    return [
        Traveller(
            id=row.id,
            name=row.name,
            me=bool(row.me),
            position=row.position,
            member_user_id=row.member_user_id,
        )
        for row in rows
    ]


class TravellerChange(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=60)] = None
    member_user_id: UUID | None = None


async def update_traveller(
    connection: AsyncConnection,
    trip_id: str,
    traveller_id: str,
    change: TravellerChange,
    members_by_space: dict[str, set[str]],
) -> list[Traveller]:
    trip = (
        await connection.execute(
            text("""
                select space_id::text as space_id, companions from travel.travel_trip
                where id = :id
            """),
            {"id": trip_id},
        )
    ).one_or_none()
    if trip is None:
        raise travel.NotFound(f"viaje {trip_id}")
    current = next(
        (one for one in await ensure_travellers(connection, trip_id) if one.id == traveller_id),
        None,
    )
    if current is None:
        raise travel.NotFound(f"viajero {traveller_id}")
    if "member_user_id" in change.model_fields_set:
        member = str(change.member_user_id) if change.member_user_id else None
        if member is not None:
            if trip.space_id is None:
                raise travel.Conflict(
                    "solo se enlaza a alguien en un viaje compartido con un espacio", "NOT_SHARED"
                )
            if member not in members_by_space.get(trip.space_id, set()):
                raise travel.Conflict("esa persona no está en el espacio del viaje", "NOT_MEMBER")
            await connection.execute(
                text("""
                    update travel.travel_traveller set member_user_id = null
                    where trip_id = :trip and member_user_id = cast(:member as uuid)
                      and id <> :id
                """),
                {"trip": trip_id, "member": member, "id": traveller_id},
            )
        await connection.execute(
            text("""
                update travel.travel_traveller set member_user_id = cast(:member as uuid)
                where id = :id
            """),
            {"id": traveller_id, "member": member},
        )
    name = " ".join(change.name.split()) if change.name else None
    if name and name != current.name:
        taken = await connection.scalar(
            text("""
                select 1 from travel.travel_traveller
                where trip_id = :trip and lower(name) = lower(:name) and id <> :id
            """),
            {"trip": trip_id, "name": name, "id": traveller_id},
        )
        if taken:
            raise travel.Conflict(f"ya hay un viajero que se llama {name}", "DUPLICATE")
        await connection.execute(
            text("update travel.travel_traveller set name = :name where id = :id"),
            {"id": traveller_id, "name": name},
        )
        companions = [name if one == current.name else one for one in trip.companions]
        if companions != list(trip.companions):
            await connection.execute(
                text("update travel.travel_trip set companions = :companions where id = :id"),
                {"id": trip_id, "companions": companions},
            )
    await travel._touch(connection, trip_id)
    return await travellers(connection, trip_id)


async def resolve_traveller(connection: AsyncConnection, trip_id: str, who: str) -> str:
    found = await ensure_travellers(connection, trip_id)
    wanted = " ".join(who.split()).lower()
    for one in found:
        if one.id == who or one.name.lower() == wanted or (one.me and wanted in ("yo", "tú", "tu")):
            return one.id
    raise travel.Conflict(
        f"no hay ningún viajero llamado «{who}»",
        "NOT_FOUND",
        [{"traveller": one.name} for one in found],
    )


async def ensure_travellers(connection: AsyncConnection, trip_id: str) -> list[Traveller]:
    trip = (
        await connection.execute(
            text("""
                select travellers, companions, user_id::text as owner
                from travel.travel_trip where id = :id
            """),
            {"id": trip_id},
        )
    ).one_or_none()
    if trip is None:
        raise travel.NotFound(f"viaje {trip_id}")
    found = await travellers(connection, trip_id)
    names = {one.name.lower() for one in found}
    wanted: list[tuple[str, str | None]] = []
    if not found:
        wanted.append(("Yo", trip.owner))
    for companion in trip.companions:
        if companion.lower() not in names:
            wanted.append((companion, None))
    count = len(found) + len(wanted)
    number = count
    while count < trip.travellers:
        number += 1
        name = f"Viajero {number}"
        if name.lower() not in names:
            wanted.append((name, None))
            count += 1
    for offset, (name, member) in enumerate(wanted):
        await connection.execute(
            text("""
                insert into travel.travel_traveller (trip_id, name, position, member_user_id)
                values (:trip, :name, :pos, cast(:member as uuid))
                on conflict (trip_id, name) do nothing
            """),
            {"trip": trip_id, "name": name, "pos": len(found) + offset, "member": member},
        )
    return await travellers(connection, trip_id)


class Converted(BaseModel):
    amount: Decimal
    currency: str
    fx_rate: Decimal
    fx_on: date
    total_eur: Decimal


async def convert(
    amount: Decimal, currency: str, day: date, manual_rate: Decimal | None = None
) -> Converted:
    currency = currency.upper()
    if currency == "EUR":
        rate, on = Decimal(1), day
    elif manual_rate is not None:
        rate, on = manual_rate, day
    else:
        found = await hub.fx(currency, day.isoformat())
        if found.get("rate") is None:
            raise travel.Conflict(
                f"no sé el cambio de {currency}: {found.get('failed') or 'sin respuesta'}. "
                "Dalo tú (euros por unidad).",
                "FX_UNKNOWN",
            )
        rate, on = Decimal(str(found["rate"])), date.fromisoformat(found["date"])
    total = (amount * rate).quantize(CENT, ROUND_HALF_UP)
    return Converted(amount=amount, currency=currency, fx_rate=rate, fx_on=on, total_eur=total)


def per_person(total_eur: Decimal, travellers_count: int) -> Decimal:
    return (total_eur / travellers_count).quantize(CENT, ROUND_HALF_UP)


async def save_shares(
    connection: AsyncConnection, trip_id: str, expense_id: str, request: travel.ExpenseIn
) -> None:
    if "shares" not in request.model_fields_set:
        return
    await connection.execute(
        text("delete from travel.travel_expense_share where expense_id = :id"), {"id": expense_id}
    )
    if not request.shares:
        return
    if request.amount is None:
        raise travel.Conflict(
            "el reparto a medida va con lo pagado en su moneda, no por persona", "INVALID"
        )
    people = {one.id for one in await travellers(connection, trip_id)}
    total = Decimal(0)
    for share in request.shares:
        if share.traveller_id not in people:
            raise travel.Conflict(
                "una parte es de alguien que no es viajero del viaje", "NOT_FOUND"
            )
        total += share.amount
    if abs(total - request.amount) > CENT:
        raise travel.Conflict(
            f"las partes suman {total} y lo pagado es {request.amount}: tienen que coincidir",
            "SHARES_MISMATCH",
        )
    for share in request.shares:
        await connection.execute(
            text("""
                insert into travel.travel_expense_share (trip_id, expense_id, traveller_id, amount)
                values (:trip, :expense, :traveller, :amount)
            """),
            {
                "trip": trip_id,
                "expense": expense_id,
                "traveller": share.traveller_id,
                "amount": share.amount,
            },
        )


class Standing(BaseModel):
    traveller: Traveller
    paid_eur: float
    share_eur: float
    net_eur: float


class Transfer(BaseModel):
    from_traveller: Traveller
    to_traveller: Traveller
    amount_eur: float


class Settlement(BaseModel):
    id: str
    from_traveller: Traveller
    to_traveller: Traveller
    amount_eur: float
    settled_on: date
    note: str | None


class Balance(BaseModel):
    people: list[Standing]
    transfers: list[Transfer]
    settlements: list[Settlement]
    unassigned_eur: float


def minimal_transfers(net: dict[str, Decimal]) -> list[tuple[str, str, Decimal]]:
    owes = sorted(
        ((who, -value) for who, value in net.items() if value < -CENT / 2), key=lambda one: -one[1]
    )
    owed = sorted(
        ((who, value) for who, value in net.items() if value > CENT / 2), key=lambda one: -one[1]
    )
    debtors = [[who, value] for who, value in owes]
    creditors = [[who, value] for who, value in owed]
    found: list[tuple[str, str, Decimal]] = []
    while debtors and creditors:
        debtor, creditor = debtors[0], creditors[0]
        amount = min(debtor[1], creditor[1]).quantize(CENT, ROUND_HALF_UP)
        if amount > 0:
            found.append((debtor[0], creditor[0], amount))
        debtor[1] -= amount
        creditor[1] -= amount
        if debtor[1] <= CENT / 2:
            debtors.pop(0)
        if creditor[1] <= CENT / 2:
            creditors.pop(0)
    return found


async def balance(connection: AsyncConnection, trip_id: str) -> Balance:
    people = await ensure_travellers(connection, trip_id)
    found = await travel.trip(connection, trip_id)
    by_id = {one.id: one for one in people}
    paid = {one.id: Decimal(0) for one in people}
    share = {one.id: Decimal(0) for one in people}
    custom = (
        await connection.execute(
            text("""
                select expense_id::text as expense_id, traveller_id::text as traveller_id, amount
                from travel.travel_expense_share where trip_id = :trip
            """),
            {"trip": trip_id},
        )
    ).all()
    parts: dict[str, list] = {}
    for row in custom:
        parts.setdefault(row.expense_id, []).append(row)
    unassigned = Decimal(0)
    for expense in found.expenses:
        total = Decimal(str(expense.total_eur or 0))
        if expense.paid_by is None or expense.paid_by not in paid:
            unassigned += total
            continue
        paid[expense.paid_by] += total
        mine = parts.get(expense.id)
        if mine and expense.amount:
            whole = Decimal(str(expense.amount))
            for row in mine:
                if row.traveller_id in share:
                    share[row.traveller_id] += total * Decimal(row.amount) / whole
        else:
            for one in people:
                share[one.id] += total / len(people)
    settled = (
        await connection.execute(
            text("""
                select id::text as id, from_traveller::text as from_id, to_traveller::text as to_id,
                       amount_eur, settled_on, note
                from travel.travel_settlement where trip_id = :trip order by settled_on, created_at
            """),
            {"trip": trip_id},
        )
    ).all()
    net = {who: paid[who] - share[who] for who in paid}
    for row in settled:
        if row.from_id in net and row.to_id in net:
            net[row.from_id] += Decimal(row.amount_eur)
            net[row.to_id] -= Decimal(row.amount_eur)
    return Balance(
        people=[
            Standing(
                traveller=one,
                paid_eur=float(paid[one.id].quantize(CENT, ROUND_HALF_UP)),
                share_eur=float(share[one.id].quantize(CENT, ROUND_HALF_UP)),
                net_eur=float(net[one.id].quantize(CENT, ROUND_HALF_UP)),
            )
            for one in people
        ],
        transfers=[
            Transfer(from_traveller=by_id[a], to_traveller=by_id[b], amount_eur=float(amount))
            for a, b, amount in minimal_transfers(net)
        ],
        settlements=[
            Settlement(
                id=row.id,
                from_traveller=by_id[row.from_id],
                to_traveller=by_id[row.to_id],
                amount_eur=float(row.amount_eur),
                settled_on=row.settled_on,
                note=row.note,
            )
            for row in settled
            if row.from_id in by_id and row.to_id in by_id
        ],
        unassigned_eur=float(unassigned.quantize(CENT, ROUND_HALF_UP)),
    )


class SettlementIn(BaseModel):
    from_traveller: str
    to_traveller: str
    amount_eur: Decimal
    settled_on: date | None = None
    note: str | None = None


async def settle(connection: AsyncConnection, trip_id: str, request: SettlementIn) -> Balance:
    people = {one.id for one in await ensure_travellers(connection, trip_id)}
    if request.from_traveller not in people or request.to_traveller not in people:
        raise travel.Conflict("quien paga o quien cobra no es viajero del viaje", "NOT_FOUND")
    if request.from_traveller == request.to_traveller:
        raise travel.Conflict("una devolución va de una persona a otra", "INVALID")
    if request.amount_eur <= 0:
        raise travel.Conflict("lo devuelto tiene que ser más que nada", "INVALID")
    await connection.execute(
        text("""
            insert into travel.travel_settlement
                (trip_id, from_traveller, to_traveller, amount_eur, settled_on, note)
            values (:trip, :from_id, :to_id, :amount, coalesce(:day, current_date), :note)
        """),
        {
            "trip": trip_id,
            "from_id": request.from_traveller,
            "to_id": request.to_traveller,
            "amount": request.amount_eur.quantize(CENT, ROUND_HALF_UP),
            "day": request.settled_on,
            "note": request.note,
        },
    )
    await travel._touch(connection, trip_id)
    return await balance(connection, trip_id)


async def unsettle(connection: AsyncConnection, trip_id: str, settlement_id: str) -> Balance:
    deleted = await connection.execute(
        text("delete from travel.travel_settlement where id = :id and trip_id = :trip"),
        {"id": settlement_id, "trip": trip_id},
    )
    if deleted.rowcount == 0:
        raise travel.NotFound(f"devolución {settlement_id}")
    await travel._touch(connection, trip_id)
    return await balance(connection, trip_id)
