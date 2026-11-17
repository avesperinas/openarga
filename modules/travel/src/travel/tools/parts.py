from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    money,
    travel,
)
from travel.tools.common import (
    BOOKING_NAMES,
    DRY_RUN,
    STAY_NAMES,
    TICKET_NAMES,
    PlaceArgument,
    StayArgs,
    TicketArgs,
    _detail,
    _edit,
    _given,
    _mutate,
    _no_null,
    _place,
    _resolve,
    _summary,
)
from travel.tools.reading import _other


class AddStay(StayArgs):
    trip_id: str
    place: PlaceArgument
    arrives_on: date
    leaves_on: date = Field(description="The day of leaving. The nights are the difference.")
    accommodation: str | None = Field(default=None, max_length=200)


async def add_stay(connection: AsyncConnection, arguments: AddStay) -> dict[str, Any]:
    async def run() -> travel.Trip:
        place = await _resolve(connection, arguments.place)
        request = travel.StayIn(
            place_id=place.id,
            arrives_on=arguments.arrives_on,
            leaves_on=arguments.leaves_on,
            accommodation=arguments.accommodation,
            **_given(arguments, *BOOKING_NAMES, *STAY_NAMES),
        )
        return await travel.add_stay(connection, arguments.trip_id, request)

    return await _edit(connection, run)


class UpdateStay(StayArgs):
    stay_id: UUID
    arrives_on: date | None = None
    leaves_on: date | None = None
    accommodation: str | None = Field(
        default=None, max_length=200, description="`null` deletes it."
    )
    place: PlaceArgument | None = Field(
        default=None,
        description=(
            "Another place: a find_place candidate or a place_id. The legs leaving or arriving "
            "here move to the new place."
        ),
    )
    dry_run: bool = DRY_RUN


async def update_stay(connection: AsyncConnection, arguments: UpdateStay) -> dict[str, Any]:
    stay_id = str(arguments.stay_id)

    async def run() -> travel.Trip:
        _no_null(arguments, "arrives_on", "leaves_on", "place")
        trip_id = await travel.trip_of(connection, "stays", stay_id)
        current = next(
            one for one in (await travel.trip(connection, trip_id)).stays if one.id == stay_id
        )
        place_id = current.place.id
        if arguments.place is not None:
            place_id = (await _resolve(connection, arguments.place)).id
        request = travel.StayIn(
            **{
                "place_id": place_id,
                "arrives_on": current.arrives_on,
                "leaves_on": current.leaves_on,
                "accommodation": current.accommodation,
                **_given(
                    arguments,
                    "arrives_on",
                    "leaves_on",
                    "accommodation",
                    *BOOKING_NAMES,
                    *STAY_NAMES,
                ),
            }
        )
        return await travel.update_stay(connection, trip_id, stay_id, request)

    return await _edit(connection, run, arguments.dry_run)


class RemoveStay(BaseModel):
    stay_id: UUID
    on_dependents: travel.OnDependents = Field(
        default="reject",
        description=(
            "What to do with the visits and legs hanging from it: reject removes nothing and says "
            "which; detach leaves the visits without a main place and the legs going to that "
            "place; delete removes them with it."
        ),
    )
    dry_run: bool = DRY_RUN


async def remove_stay(connection: AsyncConnection, arguments: RemoveStay) -> dict[str, Any]:
    stay_id = str(arguments.stay_id)

    async def run() -> dict[str, Any]:
        trip_id = await travel.trip_of(connection, "stays", stay_id)
        found, counts = await travel.remove_stay(
            connection, trip_id, stay_id, arguments.on_dependents
        )
        answer: dict[str, Any] = {"trip": _detail(found)}
        if arguments.on_dependents == "delete":
            answer["deleted_dependents"] = counts
        elif arguments.on_dependents == "detach":
            answer["detached_dependents"] = counts
        return answer

    return await _mutate(connection, run, arguments.dry_run)


class AddVisit(BaseModel):
    trip_id: str
    place: PlaceArgument
    visited_on: date | None = None
    stay_id: str | None = Field(
        default=None,
        description=(
            "From which main place. Without it, the one covering that day, if there is one."
        ),
    )
    note: str | None = Field(default=None, max_length=500)


async def add_visit(connection: AsyncConnection, arguments: AddVisit) -> dict[str, Any]:
    async def run() -> travel.Trip:
        place = await _resolve(connection, arguments.place)
        stay_id = arguments.stay_id or await travel.stay_covering(
            connection, arguments.trip_id, arguments.visited_on
        )
        request = travel.VisitIn(
            place_id=place.id, stay_id=stay_id, visited_on=arguments.visited_on, note=arguments.note
        )
        return await travel.add_visit(connection, arguments.trip_id, request)

    return await _edit(connection, run)


class UpdateVisit(BaseModel):
    visit_id: UUID
    place: PlaceArgument | None = None
    visited_on: date | None = Field(
        default=None,
        description=(
            "With another day, it moves to the main place covering that day if no stay_id is "
            "given. `null` deletes the day."
        ),
    )
    stay_id: UUID | None = Field(
        default=None, description="`null` releases it from the main place."
    )
    note: str | None = Field(default=None, max_length=500, description="`null` deletes it.")


async def update_visit(connection: AsyncConnection, arguments: UpdateVisit) -> dict[str, Any]:
    visit_id = str(arguments.visit_id)

    async def run() -> travel.Trip:
        _no_null(arguments, "place")
        trip_id = await travel.trip_of(connection, "visits", visit_id)
        current = next(
            one for one in (await travel.trip(connection, trip_id)).visits if one.id == visit_id
        )
        place_id = current.place.id
        if arguments.place is not None:
            place_id = (await _resolve(connection, arguments.place)).id
        changes = _given(arguments, "visited_on", "note")
        visited_on = changes.get("visited_on", current.visited_on)
        stay_id = current.stay_id
        if "stay_id" in arguments.model_fields_set:
            stay_id = str(arguments.stay_id) if arguments.stay_id else None
        elif visited_on is not None and visited_on != current.visited_on:
            stay_id = await travel.stay_covering(connection, trip_id, visited_on)
        request = travel.VisitIn(
            place_id=place_id,
            stay_id=stay_id,
            visited_on=visited_on,
            note=changes.get("note", current.note),
        )
        return await travel.update_visit(connection, trip_id, visit_id, request)

    return await _edit(connection, run)


class VisitRef(BaseModel):
    visit_id: UUID


class LegRef(BaseModel):
    leg_id: UUID


class ExpenseRef(BaseModel):
    expense_id: UUID


async def _remove(connection: AsyncConnection, part: str, part_id: UUID) -> dict[str, Any]:
    async def run() -> travel.Trip:
        trip_id = await travel.trip_of(connection, part, str(part_id))
        return await travel.delete_part(connection, trip_id, part, str(part_id))

    return await _edit(connection, run)


async def remove_visit(connection: AsyncConnection, arguments: VisitRef) -> dict[str, Any]:
    return await _remove(connection, "visits", arguments.visit_id)


class AddLeg(TicketArgs):
    trip_id: str
    mode: travel.Mode = Field(description="plane, train, car, bus or boat.")
    from_stay_id: str | None = Field(default=None, description="Leaves from this main place.")
    from_place: PlaceArgument | None = Field(
        default=None, description="Or from somewhere else, like home: a find_place candidate."
    )
    to_stay_id: str | None = None
    to_place: PlaceArgument | None = None
    travelled_on: date | None = None
    note: str | None = Field(default=None, max_length=500)
    on_map: bool | None = Field(
        default=None,
        description=(
            "Whether it shows in the thumbnails, the trip map and the route. If not given, or "
            "`null`, it is deduced: the way out from home and the way back are left out."
        ),
    )

    @model_validator(mode="after")
    def ends(self) -> AddLeg:
        if (self.from_stay_id is None) == (self.from_place is None):
            raise ValueError("the origin is from_stay_id or from_place, one of the two")
        if (self.to_stay_id is None) == (self.to_place is None):
            raise ValueError("the destination is to_stay_id or to_place, one of the two")
        return self


async def _end(
    connection: AsyncConnection, trip_id: str, stay_id: str | None, place: PlaceArgument | None
) -> str:
    if place is not None:
        return (await _resolve(connection, place)).id
    found = await connection.scalar(
        text("select place_id::text from travel.travel_stay where id = :id and trip_id = :trip"),
        {"id": stay_id, "trip": trip_id},
    )
    if found is None:
        raise travel.Conflict(
            "that main place is not from this trip", "NOT_FOUND", [{"stay_id": stay_id}]
        )
    return found


async def add_leg(connection: AsyncConnection, arguments: AddLeg) -> dict[str, Any]:
    async def run() -> travel.Trip:
        trip_id = arguments.trip_id
        request = travel.LegIn(
            from_place_id=await _end(
                connection, trip_id, arguments.from_stay_id, arguments.from_place
            ),
            to_place_id=await _end(connection, trip_id, arguments.to_stay_id, arguments.to_place),
            mode=arguments.mode,
            travelled_on=arguments.travelled_on,
            note=arguments.note,
            on_map=arguments.on_map,
            **_given(arguments, *BOOKING_NAMES, *TICKET_NAMES),
        )
        return await travel.add_leg(connection, trip_id, request)

    return await _edit(connection, run)


class UpdateLeg(TicketArgs):
    leg_id: UUID
    mode: travel.Mode | None = Field(default=None, description="plane, train, car, bus or boat.")
    from_stay_id: UUID | None = Field(default=None, description="Leaves from this main place.")
    from_place: PlaceArgument | None = Field(
        default=None, description="Or from somewhere else: a find_place candidate or a place_id."
    )
    to_stay_id: UUID | None = None
    to_place: PlaceArgument | None = None
    travelled_on: date | None = Field(default=None, description="`null` deletes the day.")
    note: str | None = Field(default=None, max_length=500, description="`null` deletes it.")
    on_map: bool | None = Field(
        default=None,
        description=(
            "Whether it shows in the thumbnails, the trip map and the route; `null` deduces it "
            "again: the way out from home and the way back are left out."
        ),
    )

    @model_validator(mode="after")
    def ends(self) -> UpdateLeg:
        if self.from_stay_id is not None and self.from_place is not None:
            raise ValueError("the origin is from_stay_id or from_place, not both")
        if self.to_stay_id is not None and self.to_place is not None:
            raise ValueError("the destination is to_stay_id or to_place, not both")
        return self


async def update_leg(connection: AsyncConnection, arguments: UpdateLeg) -> dict[str, Any]:
    leg_id = str(arguments.leg_id)

    async def run() -> travel.Trip:
        trip_id = await travel.trip_of(connection, "legs", leg_id)
        current = next(
            one for one in (await travel.trip(connection, trip_id)).legs if one.id == leg_id
        )
        start, end = current.from_place.id, current.to_place.id
        if arguments.from_stay_id or arguments.from_place:
            stay = str(arguments.from_stay_id) if arguments.from_stay_id else None
            start = await _end(connection, trip_id, stay, arguments.from_place)
        if arguments.to_stay_id or arguments.to_place:
            stay = str(arguments.to_stay_id) if arguments.to_stay_id else None
            end = await _end(connection, trip_id, stay, arguments.to_place)
        changes = _given(
            arguments, "mode", "travelled_on", "note", "on_map", *BOOKING_NAMES, *TICKET_NAMES
        )
        request = travel.LegIn(
            **{
                "from_place_id": start,
                "to_place_id": end,
                "mode": current.mode,
                "travelled_on": current.travelled_on,
                "note": current.note,
                "on_map": current.on_map,
                **changes,
            }
        )
        return await travel.update_leg(connection, trip_id, leg_id, request)

    return await _edit(connection, run)


async def remove_leg(connection: AsyncConnection, arguments: LegRef) -> dict[str, Any]:
    return await _remove(connection, "legs", arguments.leg_id)


class PaidArgs(BaseModel):
    amount: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="What was paid, in its currency: the total.",
    )
    currency: str | None = Field(
        default=None, pattern=r"^[A-Za-z]{3}$", description="EUR, JPY, USD, GBP…"
    )
    paid_by: str | None = Field(
        default=None,
        description='Who paid: a traveller\'s name, or "me". The travellers are in get_trip.',
    )
    spent_on: date | None = Field(
        default=None, description="The day of the expense; if not given, today."
    )
    fx_rate: Decimal | None = Field(
        default=None,
        gt=0,
        description=(
            "Euros per unit, only for a currency the ECB does not publish: if the rate is unknown,"
            " the expense is not noted and it says so."
        ),
    )
    shares: dict[str, Decimal] | None = Field(
        default=None,
        description=(
            "Custom split: {traveller's name or \"me\": their share in the expense's currency}, "
            "adding up to what was paid. If not given, equal shares; {} goes back to equal shares."
        ),
    )


async def _shares(connection: AsyncConnection, trip_id: str, arguments: PaidArgs) -> dict:
    if "shares" not in arguments.model_fields_set:
        return {}
    shares = arguments.shares or {}
    return {
        "shares": [
            travel.ShareIn(traveller_id=await _payer(connection, trip_id, who), amount=amount)
            for who, amount in shares.items()
        ]
    }


async def _payer(connection: AsyncConnection, trip_id: str, who: str | None) -> str | None:
    if who is None:
        return None
    return await money.resolve_traveller(connection, trip_id, who)


class RecordTripExpense(PaidArgs):
    trip_id: str
    category: travel.Category = Field(
        description=(
            "transport (flights, car, fuel and parking, ferry, train, bus), lodging (hotel, "
            "apartment) or other (cash, excursions, insurance and vaccines, other)."
        )
    )
    concept: str = Field(min_length=1, max_length=60, description="Flights, Hotel, Excursions…")
    amount_eur_per_person: Decimal | None = Field(
        default=None,
        ge=0,
        le=Decimal("99999999"),
        decimal_places=2,
        description="Per person and already in euros, as in the sheet. Or amount and currency.",
    )
    note: str | None = Field(default=None, max_length=300)


async def record_trip_expense(
    connection: AsyncConnection, arguments: RecordTripExpense
) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        request = travel.ExpenseIn(
            category=arguments.category,
            concept=arguments.concept,
            amount_eur=arguments.amount_eur_per_person,
            amount=arguments.amount,
            currency=arguments.currency.upper() if arguments.currency else None,
            fx_rate=arguments.fx_rate,
            spent_on=arguments.spent_on,
            paid_by=await _payer(connection, arguments.trip_id, arguments.paid_by),
            note=arguments.note,
            **await _shares(connection, arguments.trip_id, arguments),
        )
        expense_id, found = await travel.record_expense(
            connection, arguments.trip_id, request, source="tool"
        )
        detail = _detail(found)
        return {
            "recorded": True,
            "expense_id": expense_id,
            "spend": detail["spend"],
            "trip": detail,
        }

    return await _mutate(connection, run)


class UpdateExpense(PaidArgs):
    expense_id: UUID
    amount_eur_per_person: Decimal | None = Field(
        default=None,
        ge=0,
        le=Decimal("99999999"),
        decimal_places=2,
        description="Per person and already in euros.",
    )
    category: travel.Category | None = Field(
        default=None, description="transport, lodging u other."
    )
    concept: str | None = Field(default=None, min_length=1, max_length=60)
    note: str | None = Field(default=None, max_length=300, description="`null` deletes it.")


async def update_expense(connection: AsyncConnection, arguments: UpdateExpense) -> dict[str, Any]:
    expense_id = str(arguments.expense_id)

    async def run() -> travel.Trip:
        trip_id = await travel.trip_of(connection, "expenses", expense_id)
        current = next(
            one for one in (await travel.trip(connection, trip_id)).expenses if one.id == expense_id
        )
        changes = _given(arguments, "category", "concept", "note")
        paid = {"amount", "currency", "paid_by", "spent_on", "fx_rate"}
        if "amount_eur_per_person" in arguments.model_fields_set:
            base = {"amount_eur": arguments.amount_eur_per_person}
        else:
            moved = bool({"currency", "spent_on"} & arguments.model_fields_set)
            base = {
                "amount": Decimal(str(current.amount)) if current.amount is not None else None,
                "currency": current.currency,
                "fx_rate": None
                if moved or current.fx_rate is None
                else Decimal(str(current.fx_rate)),
                "spent_on": current.spent_on,
                "paid_by": current.paid_by,
                "amount_eur": Decimal(str(current.amount_eur)),
            }
            given = _given(arguments, *paid)
            if "currency" in given and given["currency"]:
                given["currency"] = given["currency"].upper()
            if "paid_by" in given:
                given["paid_by"] = await _payer(connection, trip_id, given["paid_by"])
            base.update(given)
            if base["amount"] is None:
                base.pop("amount")
        request = travel.ExpenseIn(
            **{
                "category": current.category,
                "concept": current.concept,
                "note": current.note,
                **base,
                **changes,
                **await _shares(connection, trip_id, arguments),
            }
        )
        return await travel.update_expense(connection, trip_id, expense_id, request)

    return await _edit(connection, run)


async def remove_expense(connection: AsyncConnection, arguments: ExpenseRef) -> dict[str, Any]:
    return await _remove(connection, "expenses", arguments.expense_id)


class AddOtherPlace(BaseModel):
    place: PlaceArgument
    note: str | None = Field(
        default=None,
        max_length=300,
        description="What is remembered: with whom, around which year.",
    )


async def add_other_place(connection: AsyncConnection, arguments: AddOtherPlace) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        place = await _resolve(connection, arguments.place)
        other = await travel.add_other_place(
            connection, travel.OtherPlaceIn(place_id=place.id, note=arguments.note), source="tool"
        )
        return _other(other)

    return await _mutate(connection, run)


class OtherPlaceRef(BaseModel):
    other_place_id: UUID = Field(
        description="The one given by get_travel (other_places) and add_other_place."
    )


async def _current_other(connection: AsyncConnection, other_id: str) -> travel.OtherPlace:
    found = next((one for one in await travel.other_places(connection) if one.id == other_id), None)
    if found is None:
        raise travel.NotFound(f"place without a trip {other_id}")
    return found


class UpdateOtherPlace(OtherPlaceRef):
    place: PlaceArgument | None = None
    note: str | None = Field(default=None, max_length=300, description="`null` deletes it.")


async def update_other_place(
    connection: AsyncConnection, arguments: UpdateOtherPlace
) -> dict[str, Any]:
    other_id = str(arguments.other_place_id)

    async def run() -> dict[str, Any]:
        _no_null(arguments, "place")
        current = await _current_other(connection, other_id)
        place_id = current.place.id
        if arguments.place is not None:
            place_id = (await _resolve(connection, arguments.place)).id
        note = _given(arguments, "note").get("note", current.note)
        request = travel.OtherPlaceIn(place_id=place_id, note=note)
        return _other(await travel.update_other_place(connection, other_id, request))

    return await _mutate(connection, run)


async def remove_other_place(connection: AsyncConnection, arguments: OtherPlaceRef) -> dict:
    other_id = str(arguments.other_place_id)

    async def run() -> dict[str, Any]:
        current = await _current_other(connection, other_id)
        await travel.delete_other_place(connection, other_id)
        return {"removed": _other(current)}

    return await _mutate(connection, run)


CATEGORY_HELP = (
    "The kind of place: restaurant, nightlife (bars and night), cafe, market, beach, nature "
    "(nature and trails), viewpoint, culture (museums, churches, monuments), castle (castles and "
    "ruins), town (village or city), shopping, parking, lodging or other."
)


class UpdatePlace(BaseModel):
    place_id: UUID
    name: str | None = Field(
        default=None, min_length=1, max_length=120, description="Another name."
    )
    candidate: travel.PlaceIn | None = Field(
        default=None,
        description=(
            "A find_place candidate as is, to resolve it again: coordinates, country, region and "
            "kilometres are redone. With name, the name is that one and not the candidate's."
        ),
    )
    category: travel.PlaceCategory | None = Field(default=None, description=CATEGORY_HELP)
    dry_run: bool = DRY_RUN

    @model_validator(mode="after")
    def something(self) -> UpdatePlace:
        if self.name is None and self.candidate is None and self.category is None:
            raise ValueError("a new name, a find_place candidate or a kind is needed")
        return self


async def update_place(connection: AsyncConnection, arguments: UpdatePlace) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        place, affected = await travel.update_place(
            connection,
            str(arguments.place_id),
            arguments.name,
            arguments.candidate,
            arguments.category,
        )
        return {
            "place": _place(place),
            "affected_trips": [_summary(await travel.trip(connection, one)) for one in affected],
        }

    return await _mutate(connection, run, arguments.dry_run)
