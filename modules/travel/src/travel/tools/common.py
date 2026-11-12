from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    travel,
)

MODULE = "travel"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _summary(one: travel.Trip) -> dict[str, Any]:
    return {
        "trip_id": one.id,
        "title": one.title,
        "starts_on": one.starts_on.isoformat(),
        "ends_on": one.ends_on.isoformat(),
        "nights": one.nights,
        "travellers": one.travellers,
        "companions": one.companions,
        "tags": one.tags,
        "countries": one.countries,
        "stays": [stay.place.name for stay in one.stays],
        "km": one.km,
        "spend_per_person_eur": one.spend.per_person,
        "cost_per_day_eur": one.spend.per_day,
        "budget_per_person_eur": one.budget_eur,
        "budget_left_per_person_eur": round(one.budget_eur - one.spend.per_person, 2)
        if one.budget_eur is not None
        else None,
        "archived": one.archived,
        "phase": one.phase,
        "shared": one.space_id is not None,
        "mine": one.mine,
    }


def _place(place: travel.Place) -> dict[str, Any]:
    return {
        "place_id": place.id,
        "name": place.name,
        "country": place.country_code,
        "region": place.region_code,
        "category": place.category,
        "resolved": place.lat is not None,
    }


def _booking(found: Any) -> dict[str, Any]:
    return {
        key: getattr(found, key)
        for key in ("confirmation", "provider", "booking_url", "cost_eur", "paid_by")
        if getattr(found, key, None) is not None
    }


def _hhmm(value: Any) -> str | None:
    return value.strftime("%H:%M") if value else None


def _detail(one: travel.Trip) -> dict[str, Any]:
    return {
        **_summary(one),
        "notes": one.notes,
        "summary": one.summary,
        "cover": None
        if one.cover is None
        else {"from_wikimedia": one.cover.page is not None}
        | ({"author": one.cover.author, "page": one.cover.page} if one.cover.page else {}),
        "stays": [
            {
                "stay_id": stay.id,
                **_place(stay.place),
                "arrives_on": stay.arrives_on.isoformat(),
                "leaves_on": stay.leaves_on.isoformat(),
                "nights": stay.nights,
                "accommodation": stay.accommodation,
                "check_in_at": _hhmm(stay.check_in_at),
                "check_out_at": _hhmm(stay.check_out_at),
                "address": stay.address,
                **_booking(stay),
            }
            for stay in one.stays
        ],
        "visits": [
            {
                "visit_id": visit.id,
                **_place(visit.place),
                "stay_id": visit.stay_id,
                "visited_on": visit.visited_on.isoformat() if visit.visited_on else None,
                "note": visit.note,
            }
            for visit in one.visits
        ],
        "legs": [
            {
                "leg_id": leg.id,
                "from": leg.from_place.name,
                "to": leg.to_place.name,
                "from_stay_id": leg.from_stay_id,
                "to_stay_id": leg.to_stay_id,
                "from_place_id": leg.from_place.id,
                "to_place_id": leg.to_place.id,
                "mode": leg.mode,
                "travelled_on": leg.travelled_on.isoformat() if leg.travelled_on else None,
                "km": leg.km,
                "note": leg.note,
                "on_map": leg.on_map,
                "departs_at": _hhmm(leg.departs_at),
                "arrives_on": leg.arrives_on.isoformat() if leg.arrives_on else None,
                "arrives_at": _hhmm(leg.arrives_at),
                **{
                    key: getattr(leg, key)
                    for key in (
                        "carrier",
                        "number",
                        "from_code",
                        "to_code",
                        "terminal",
                        "seat",
                        "ticket_leg_id",
                    )
                    if getattr(leg, key)
                },
                **_booking(leg),
            }
            for leg in one.legs
        ],
        "expenses": [
            {
                "expense_id": expense.id,
                "category": expense.category,
                "concept": expense.concept,
                "amount_eur_per_person": expense.amount_eur,
                "paid": {
                    "amount": expense.amount,
                    "currency": expense.currency,
                    "total_eur": expense.total_eur,
                    "fx_rate": expense.fx_rate,
                    "fx_on": expense.fx_on.isoformat() if expense.fx_on else None,
                    "spent_on": expense.spent_on.isoformat() if expense.spent_on else None,
                    "paid_by": expense.paid_by_name,
                },
                "note": expense.note,
                "mine": expense.mine,
                **{
                    key: getattr(expense, key)
                    for key in ("stay_id", "leg_id", "block_id")
                    if getattr(expense, key)
                },
            }
            for expense in one.expenses
        ],
        "spend": {
            "per_person_eur": one.spend.per_person,
            "group_eur": one.spend.group,
            "per_day_eur": one.spend.per_day,
            "by_category_per_person_eur": one.spend.by_category,
        },
    }


def _in_range(one: travel.Trip, since: date | None, until: date | None) -> bool:
    return (since is None or one.ends_on >= since) and (until is None or one.starts_on <= until)


def _error(error: travel.NotFound | travel.Conflict) -> dict[str, Any]:
    message = f"no existe: {error}" if isinstance(error, travel.NotFound) else str(error)
    answer: dict[str, Any] = {"error": message, "code": error.code}
    if error.conflicts:
        answer["conflicts"] = error.conflicts
    return answer


async def _mutate(
    connection: AsyncConnection,
    action: Callable[[], Awaitable[dict[str, Any]]],
    dry_run: bool = False,
) -> dict[str, Any]:
    savepoint = await connection.begin_nested()
    try:
        answer = await action()
    except (travel.NotFound, travel.Conflict) as error:
        await savepoint.rollback()
        return _error(error)
    except ValidationError as error:
        await savepoint.rollback()
        return {"error": "; ".join(one["msg"] for one in error.errors()), "code": "INVALID"}
    if dry_run:
        await savepoint.rollback()
        return {"dry_run": True, **answer}
    await savepoint.commit()
    return answer


async def _edit(
    connection: AsyncConnection,
    action: Callable[[], Awaitable[travel.Trip]],
    dry_run: bool = False,
) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        return {"trip": _detail(await action())}

    return await _mutate(connection, run, dry_run)


def _given(arguments: BaseModel, *names: str) -> dict[str, Any]:
    return {name: getattr(arguments, name) for name in names if name in arguments.model_fields_set}


def _no_null(arguments: BaseModel, *names: str) -> None:
    for name in names:
        if name in arguments.model_fields_set and getattr(arguments, name) is None:
            raise travel.Conflict(f"{name} no se puede vaciar", "INVALID")


DRY_RUN = Field(
    default=False, description="Ensayo: devuelve lo que pasaría, igual que de verdad, sin escribir."
)


class PlaceArgument(travel.PlaceIn):
    name: str = Field(default="", max_length=120)
    place_id: str | None = None

    @model_validator(mode="after")
    def something(self) -> PlaceArgument:
        if not self.place_id and not self.name.strip():
            raise ValueError("hace falta un place_id o un candidato de find_place con su nombre")
        return self


async def _resolve(connection: AsyncConnection, place: PlaceArgument) -> travel.Place:
    if place.place_id:
        if place.category is not None:
            return await travel.set_category(connection, place.place_id, place.category)
        return await travel.place_by_id(connection, place.place_id)
    return await travel.save_place(
        connection, travel.PlaceIn(**place.model_dump(exclude={"place_id"}))
    )


SUMMARY_HELP = (
    "Un párrafo que cuenta el viaje, el de su portada: «Cuatro días en pareja: termas, ruin bars y "
    "el Danubio de noche». Hasta 1000 caracteres."
)


class BookingArgs(BaseModel):
    confirmation: str | None = Field(default=None, max_length=60, description="El localizador.")
    provider: str | None = Field(
        default=None, max_length=80, description="Dónde se reservó: Booking, Renfe, la aerolínea…"
    )
    booking_url: str | None = Field(default=None, max_length=500, pattern=r"^https?://")
    cost_eur: Decimal | None = Field(
        default=None,
        ge=0,
        le=Decimal("99999999"),
        decimal_places=2,
        description="Lo que costó al grupo, en euros. Se apunta como gasto de la reserva, por "
        "persona entre los viajeros; null lo quita.",
    )
    paid_by: str | None = Field(
        default=None,
        max_length=60,
        description="Quién la pagó: el nombre de un viajero o «yo». Va con cost_eur y entra en el "
        "reparto como cualquier gasto.",
    )


BOOKING_NAMES = ("confirmation", "provider", "booking_url", "cost_eur", "paid_by")
STAY_NAMES = ("check_in_at", "check_out_at", "address")
TICKET_NAMES = (
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
)


class StayArgs(BookingArgs):
    check_in_at: time | None = Field(default=None, description="HH:MM")
    check_out_at: time | None = Field(default=None, description="HH:MM")
    address: str | None = Field(default=None, max_length=300)


class TicketArgs(BookingArgs):
    departs_at: time | None = Field(default=None, description="HH:MM, hora local de salida.")
    arrives_on: date | None = Field(
        default=None, description="El día que llega, si no es el de salida: un vuelo de noche."
    )
    arrives_at: time | None = Field(default=None, description="HH:MM, hora local de llegada.")
    carrier: str | None = Field(default=None, max_length=80, description="Aerolínea, Renfe…")
    number: str | None = Field(
        default=None, max_length=40, description="IB3166, AVE 03071… Hasta 40 caracteres."
    )
    from_code: str | None = Field(
        default=None, max_length=40, description="MAD, KIX, Madrid-Atocha… Hasta 40."
    )
    to_code: str | None = Field(default=None, max_length=40, description="Hasta 40.")
    terminal: str | None = Field(default=None, max_length=40, description="T4, 2B… Hasta 40.")
    seat: str | None = Field(
        default=None, max_length=80, description="18A, 18B o los de todo el grupo. Hasta 80."
    )
    ticket_leg_id: str | None = Field(
        default=None,
        description="El leg_id del trayecto que lleva el billete, si este va en el mismo: la "
        "vuelta de un ida y vuelta o el segundo tren de un transbordo. El localizador y el coste "
        "van solo en aquel; los dos lo enseñan. null lo suelta.",
    )


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[[AsyncConnection, Any], Awaitable[dict[str, Any]]]
