from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from travel import ideas, travel
from travel.travel.places import PlaceIn, save_place

PLACES = {
    "bruges": PlaceIn(
        name="Bruges", lat=51.2093, lon=3.2247, country_code="BE", region_code="BE-VLG", kind="city"
    ),
    "ghent": PlaceIn(
        name="Ghent", lat=51.0543, lon=3.7174, country_code="BE", region_code="BE-VLG", kind="city"
    ),
    "damme": PlaceIn(
        name="Damme", lat=51.2516, lon=3.2817, country_code="BE", region_code="BE-VLG", kind="town"
    ),
    "lisbon": PlaceIn(
        name="Lisbon", lat=38.7223, lon=-9.1393, country_code="PT", region_code="PT-11", kind="city"
    ),
    "porto": PlaceIn(
        name="Porto", lat=41.1579, lon=-8.6291, country_code="PT", region_code="PT-13", kind="city"
    ),
    "kyoto": PlaceIn(
        name="Kyoto", lat=35.0116, lon=135.7681, country_code="JP", region_code="JP-26", kind="city"
    ),
}


async def _place(connection: AsyncConnection, key: str) -> str:
    return (await save_place(connection, PLACES[key])).id


async def _flanders(connection: AsyncConnection, today: date) -> None:
    start = today - timedelta(days=60)
    trip = await travel.create_trip(
        connection,
        travel.TripIn(
            title="Flanders in spring",
            starts_on=start,
            ends_on=start + timedelta(days=3),
            travellers=2,
            companions=["Sam"],
            tags=["getaway"],
            summary="Three nights of canals, belfries and too many waffles.",
            status="confirmed",
        ),
    )
    bruges, ghent = await _place(connection, "bruges"), await _place(connection, "ghent")
    found = await travel.add_stay(
        connection,
        trip.id,
        travel.StayIn(
            place_id=bruges,
            arrives_on=start,
            leaves_on=start + timedelta(days=2),
            accommodation="A small hotel by the canal",
        ),
    )
    await travel.add_stay(
        connection,
        trip.id,
        travel.StayIn(
            place_id=ghent,
            arrives_on=start + timedelta(days=2),
            leaves_on=start + timedelta(days=3),
        ),
    )
    await travel.add_visit(
        connection,
        trip.id,
        travel.VisitIn(
            place_id=await _place(connection, "damme"),
            stay_id=found.stays[0].id,
            visited_on=start + timedelta(days=1),
            note="By bike along the canal",
        ),
    )
    await travel.add_leg(
        connection,
        trip.id,
        travel.LegIn(
            from_place_id=bruges,
            to_place_id=ghent,
            mode="train",
            travelled_on=start + timedelta(days=2),
        ),
    )
    for category, concept, amount in (
        ("lodging", "Hotel", "180"),
        ("transport", "Train", "9"),
        ("other", "Excursions", "24"),
    ):
        await travel.add_expense(
            connection,
            trip.id,
            travel.ExpenseIn(
                category=category,
                concept=concept,
                amount_eur=Decimal(amount),
                spent_on=start + timedelta(days=1),
            ),
        )


async def _lisbon(connection: AsyncConnection, today: date) -> None:
    start = today + timedelta(days=30)
    trip = await travel.create_trip(
        connection,
        travel.TripIn(
            title="A long weekend in Lisbon",
            starts_on=start,
            ends_on=start + timedelta(days=3),
            status="plan",
            budget_eur=Decimal("450"),
        ),
    )
    await travel.add_stay(
        connection,
        trip.id,
        travel.StayIn(
            place_id=await _place(connection, "lisbon"),
            arrives_on=start,
            leaves_on=start + timedelta(days=3),
        ),
    )


async def _porto(connection: AsyncConnection, today: date) -> None:
    start = today - timedelta(days=120)
    trip = await travel.create_trip(
        connection,
        travel.TripIn(
            title="Porto with friends",
            starts_on=start,
            ends_on=start + timedelta(days=2),
            travellers=3,
            status="confirmed",
        ),
    )
    await travel.add_stay(
        connection,
        trip.id,
        travel.StayIn(
            place_id=await _place(connection, "porto"),
            arrives_on=start,
            leaves_on=start + timedelta(days=2),
            accommodation="A flat in Ribeira",
        ),
    )
    await travel.add_expense(
        connection,
        trip.id,
        travel.ExpenseIn(category="lodging", concept="Apartment", amount_eur=Decimal("95")),
    )


async def _japan(connection: AsyncConnection) -> None:
    made = await ideas.create_idea(
        connection,
        ideas.IdeaIn(
            title="Japan in autumn",
            budget_eur=Decimal("2500"),
            days_min=12,
            days_max=16,
            months=[10, 11],
            tags=["far"],
        ),
    )
    await ideas.add_place(connection, made.id, await _place(connection, "kyoto"), "The maples")


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    titles = {one.title for one in await travel.all_trips(connection)}
    if persona.key == "alex":
        if "Flanders in spring" not in titles:
            await _flanders(connection, today)
        if "A long weekend in Lisbon" not in titles:
            await _lisbon(connection, today)
        return
    if "Porto with friends" not in titles:
        await _porto(connection, today)
    if not any(one.title == "Japan in autumn" for one in await ideas.ideas(connection)):
        await _japan(connection)
