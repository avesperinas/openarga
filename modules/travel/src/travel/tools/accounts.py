from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    money,
)
from travel.tools.common import _mutate
from travel.tools.parts import _payer
from travel.tools.reading import GetTrip, _pick


class UpdateTraveller(BaseModel):
    trip_id: str
    traveller: str = Field(description="El viajero: su nombre actual o «yo».")
    name: str = Field(min_length=1, max_length=60, description="Cómo se llama ahora.")


async def update_traveller(
    connection: AsyncConnection, arguments: UpdateTraveller
) -> dict[str, Any]:

    async def run() -> dict[str, Any]:
        traveller_id = await _payer(connection, arguments.trip_id, arguments.traveller)
        found = await money.update_traveller(
            connection,
            arguments.trip_id,
            traveller_id,
            money.TravellerChange(name=arguments.name),
            {},
        )
        return {"travellers": ["yo" if one.me else one.name for one in found]}

    return await _mutate(connection, run)


def _balance(found: money.Balance) -> dict[str, Any]:
    name = lambda one: "yo" if one.me else one.name  # noqa: E731
    return {
        "people": [
            {
                "traveller": name(one.traveller),
                "paid_eur": one.paid_eur,
                "share_eur": one.share_eur,
                "net_eur": one.net_eur,
            }
            for one in found.people
        ],
        "transfers": [
            {
                "from": name(one.from_traveller),
                "to": name(one.to_traveller),
                "amount_eur": one.amount_eur,
            }
            for one in found.transfers
        ],
        "settlements": [
            {
                "settlement_id": one.id,
                "from": name(one.from_traveller),
                "to": name(one.to_traveller),
                "amount_eur": one.amount_eur,
                "settled_on": one.settled_on.isoformat(),
                "note": one.note,
            }
            for one in found.settlements
        ],
        "unassigned_eur": found.unassigned_eur,
    }


async def get_trip_balance(connection: AsyncConnection, arguments: GetTrip) -> dict[str, Any]:
    picked = await _pick(connection, arguments.trip_id, arguments.title)
    if "trip" not in picked:
        return picked
    if not await money.travellers(connection, picked["trip"].id):
        return {
            "people": [],
            "transfers": [],
            "settlements": [],
            "unassigned_eur": 0.0,
            "note": "nadie ha pagado nada con nombre todavía",
        }
    return _balance(await money.balance(connection, picked["trip"].id))


class RecordSettlement(BaseModel):
    trip_id: str
    from_traveller: str = Field(description="Quién devolvió: el nombre de un viajero o «yo».")
    to_traveller: str = Field(description="A quién.")
    amount_eur: Decimal = Field(gt=0, decimal_places=2)
    settled_on: date | None = None
    note: str | None = Field(default=None, max_length=300)


async def record_settlement(
    connection: AsyncConnection, arguments: RecordSettlement
) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        request = money.SettlementIn(
            from_traveller=await _payer(connection, arguments.trip_id, arguments.from_traveller),
            to_traveller=await _payer(connection, arguments.trip_id, arguments.to_traveller),
            amount_eur=arguments.amount_eur,
            settled_on=arguments.settled_on,
            note=arguments.note,
        )
        return {"balance": _balance(await money.settle(connection, arguments.trip_id, request))}

    return await _mutate(connection, run)


class RemoveSettlement(BaseModel):
    trip_id: str
    settlement_id: UUID


async def remove_settlement(
    connection: AsyncConnection, arguments: RemoveSettlement
) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        found = await money.unsettle(connection, arguments.trip_id, str(arguments.settlement_id))
        return {"balance": _balance(found)}

    return await _mutate(connection, run)
