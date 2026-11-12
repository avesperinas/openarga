from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    itinerary,
    travel,
)
from travel.tools.common import (
    BOOKING_NAMES,
    DRY_RUN,
    STAY_NAMES,
    SUMMARY_HELP,
    TICKET_NAMES,
    BookingArgs,
    PlaceArgument,
    StayArgs,
    TicketArgs,
    _given,
    _mutate,
    _resolve,
    _summary,
)
from travel.tools.days import KIND, _itinerary


class PlanStay(StayArgs):
    place: PlaceArgument
    arrives_on: date
    leaves_on: date
    accommodation: str | None = Field(default=None, max_length=200)


class PlanLeg(TicketArgs):
    mode: travel.Mode = Field(description="plane, train, car, bus o boat.")
    from_place: PlaceArgument
    to_place: PlaceArgument
    travelled_on: date | None = None
    note: str | None = Field(default=None, max_length=500)
    on_map: bool | None = None
    same_ticket_as: int | None = Field(
        default=None,
        ge=0,
        description="El puesto (desde 0) en `legs` del trayecto que lleva el billete de este: la "
        "vuelta de un ida y vuelta. Va antes en la lista.",
    )


class PlanBlock(BookingArgs):
    title: str = Field(min_length=1, max_length=120)
    kind: itinerary.Kind = KIND
    starts_at: time | None = Field(default=None, description="HH:MM.")
    ends_at: time | None = None
    place: PlaceArgument | None = Field(
        default=None, description="Un candidato de find_place, con su `category` si se sabe."
    )
    notes: str | None = Field(default=None, max_length=2000)


class PlanDay(BaseModel):
    day: date
    title: str | None = Field(default=None, max_length=80)
    blocks: list[PlanBlock] = Field(default=[], max_length=60)


class PlanTrip(BaseModel):
    trip_id: str | None = Field(
        default=None, description="Un viaje que ya existe; sin él, se crea con lo de abajo."
    )
    title: str | None = Field(default=None, min_length=1, max_length=120)
    starts_on: date | None = None
    ends_on: date | None = None
    travellers: int = Field(default=1, ge=1, le=50)
    companions: list[str] = Field(default=[], max_length=30)
    tags: list[str] = Field(default=[], max_length=20)
    summary: str | None = Field(default=None, max_length=1000, description=SUMMARY_HELP)
    status: travel.Status = Field(
        default="plan", description="plan por defecto: no sale en Planner."
    )
    budget_eur_per_person: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    stays: list[PlanStay] = Field(default=[], max_length=40)
    legs: list[PlanLeg] = Field(default=[], max_length=40)
    days: list[PlanDay] = Field(default=[], max_length=120)
    saved: list[PlanBlock] = Field(
        default=[], max_length=100, description="Sitios guardados sin día, para cuando haya hueco."
    )
    dry_run: bool = DRY_RUN

    @model_validator(mode="after")
    def which(self) -> PlanTrip:
        if self.trip_id is None and not (self.title and self.starts_on and self.ends_on):
            raise ValueError("hace falta trip_id, o title, starts_on y ends_on para crearlo")
        return self


def _where(label: str, error: travel.Conflict | travel.NotFound) -> travel.Conflict:
    return travel.Conflict(f"{label}: {error}", getattr(error, "code", "INVALID"), error.conflicts)


async def plan_trip(connection: AsyncConnection, arguments: PlanTrip) -> dict[str, Any]:

    async def step(label: str, action: Callable[[], Awaitable[Any]]) -> Any:
        try:
            return await action()
        except (travel.Conflict, travel.NotFound) as error:
            raise _where(label, error) from error
        except ValidationError as error:
            raise travel.Conflict(
                f"{label}: " + "; ".join(one["msg"] for one in error.errors()), "INVALID"
            ) from error

    async def run() -> dict[str, Any]:
        counts = {"stays": 0, "legs": 0, "day_titles": 0, "blocks": 0, "saved": 0}
        if arguments.trip_id:
            trip_id = (await travel.trip(connection, arguments.trip_id)).id
            created = False
        else:
            made = await step(
                "trip",
                lambda: travel.create_trip(
                    connection,
                    travel.TripIn(
                        title=arguments.title,
                        starts_on=arguments.starts_on,
                        ends_on=arguments.ends_on,
                        travellers=arguments.travellers,
                        companions=arguments.companions,
                        tags=arguments.tags,
                        summary=arguments.summary,
                        status=arguments.status,
                        budget_eur=arguments.budget_eur_per_person,
                    ),
                    source="tool",
                ),
            )
            trip_id, created = made.id, True
        for index, stay in enumerate(arguments.stays):

            async def add_one_stay(stay: PlanStay = stay) -> None:
                place = await _resolve(connection, stay.place)
                await travel.add_stay(
                    connection,
                    trip_id,
                    travel.StayIn(
                        place_id=place.id,
                        arrives_on=stay.arrives_on,
                        leaves_on=stay.leaves_on,
                        accommodation=stay.accommodation,
                        **_given(stay, *BOOKING_NAMES, *STAY_NAMES),
                    ),
                )

            await step(f"stays[{index}]", add_one_stay)
            counts["stays"] += 1
        leg_ids: list[str] = []
        for index, leg in enumerate(arguments.legs):

            async def add_one_leg(leg: PlanLeg = leg) -> str:
                if leg.same_ticket_as is not None and leg.same_ticket_as >= len(leg_ids):
                    raise travel.Conflict(
                        "same_ticket_as apunta a un trayecto que no va antes en la lista",
                        "INVALID",
                    )
                before = {one.id for one in (await travel.trip(connection, trip_id)).legs}
                extra = (
                    {"ticket_leg_id": leg_ids[leg.same_ticket_as]}
                    if leg.same_ticket_as is not None
                    else {}
                )
                found = await travel.add_leg(
                    connection,
                    trip_id,
                    travel.LegIn(
                        from_place_id=(await _resolve(connection, leg.from_place)).id,
                        to_place_id=(await _resolve(connection, leg.to_place)).id,
                        mode=leg.mode,
                        travelled_on=leg.travelled_on,
                        note=leg.note,
                        on_map=leg.on_map,
                        **_given(leg, *BOOKING_NAMES, *TICKET_NAMES),
                        **extra,
                    ),
                )
                return next(one.id for one in found.legs if one.id not in before)

            leg_ids.append(await step(f"legs[{index}]", add_one_leg))
            counts["legs"] += 1

        async def add_one_block(block: PlanBlock, day: date | None) -> None:
            place = await _resolve(connection, block.place) if block.place else None
            await itinerary.add_block(
                connection,
                trip_id,
                itinerary.BlockIn(
                    **block.model_dump(exclude={"place"}, exclude_unset=True),
                    day=day,
                    place_id=place.id if place else None,
                ),
            )

        for d_index, day in enumerate(arguments.days):
            if day.title:
                await step(
                    f"days[{d_index}]",
                    lambda day=day: itinerary.set_day_title(
                        connection, trip_id, day.day, day.title
                    ),
                )
                counts["day_titles"] += 1
            for b_index, block in enumerate(day.blocks):
                await step(
                    f"days[{d_index}].blocks[{b_index}]",
                    lambda block=block, day=day: add_one_block(block, day.day),
                )
                counts["blocks"] += 1
        for s_index, block in enumerate(arguments.saved):
            await step(f"saved[{s_index}]", lambda block=block: add_one_block(block, None))
            counts["saved"] += 1
        return {
            "created_trip": created,
            "trip": _summary(await travel.trip(connection, trip_id)),
            "added": counts,
            "itinerary": _itinerary(await itinerary.itinerary(connection, trip_id)),
        }

    return await _mutate(connection, run, arguments.dry_run)
