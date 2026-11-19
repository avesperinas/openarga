from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from arga_tenancy import current_spaces
from travel import ideas, itinerary, journal, lists, money, notes, travel
from travel.travel.places import PlaceIn, save_place

SAM = UUID("5a305a30-0000-4000-8000-000000005a30")

CITIES = {
    "pamplona": ("Pamplona", 42.8125, -1.6458, "ES", "city"),
    "seville": ("Seville", 37.3891, -5.9845, "ES", "city"),
    "cordoba": ("Cordoba", 37.8882, -4.7794, "ES", "city"),
    "granada": ("Granada", 37.1773, -3.5986, "ES", "city"),
    "rome": ("Rome", 41.9028, 12.4964, "IT", "city"),
    "tivoli": ("Tivoli", 41.9637, 12.7973, "IT", "town"),
    "berlin": ("Berlin", 52.52, 13.405, "DE", "city"),
    "isaba": ("Isaba", 42.9167, -0.9333, "ES", "village"),
    "torla": ("Torla", 42.6314, -0.1051, "ES", "village"),
    "bruges": ("Bruges", 51.2093, 3.2247, "BE", "city"),
    "ghent": ("Ghent", 51.0543, 3.7174, "BE", "city"),
    "damme": ("Damme", 51.2516, 3.2817, "BE", "town"),
    "copenhagen": ("Copenhagen", 55.6761, 12.5683, "DK", "city"),
    "roskilde": ("Roskilde", 55.6415, 12.0803, "DK", "town"),
    "lisbon": ("Lisbon", 38.7223, -9.1393, "PT", "city"),
    "sintra": ("Sintra", 38.7978, -9.3873, "PT", "town"),
    "bolzano": ("Bolzano", 46.4983, 11.3548, "IT", "city"),
    "ortisei": ("Ortisei", 46.5746, 11.6713, "IT", "town"),
    "porto": ("Porto", 41.1579, -8.6291, "PT", "city"),
    "paris": ("Paris", 48.8566, 2.3522, "FR", "city"),
    "versailles": ("Versailles", 48.8049, 2.1204, "FR", "town"),
    "tenerife": ("Santa Cruz de Tenerife", 28.4636, -16.2518, "ES", "city"),
    "teide": ("Teide National Park", 28.2723, -16.6425, "ES", "park"),
    "marrakech": ("Marrakech", 31.6295, -7.9811, "MA", "city"),
    "essaouira": ("Essaouira", 31.5085, -9.7595, "MA", "town"),
    "prague": ("Prague", 50.0755, 14.4378, "CZ", "city"),
    "kutna": ("Kutna Hora", 49.9484, 15.2682, "CZ", "town"),
    "kyoto": ("Kyoto", 35.0116, 135.7681, "JP", "city"),
    "nara": ("Nara", 34.6851, 135.8048, "JP", "city"),
    "reykjavik": ("Reykjavik", 64.1466, -21.9426, "IS", "city"),
    "vik": ("Vik", 63.4186, -19.006, "IS", "village"),
    "cusco": ("Cusco", -13.5319, -71.9675, "PE", "city"),
    "edinburgh": ("Edinburgh", 55.9533, -3.1883, "GB", "city"),
    "fortwilliam": ("Fort William", 56.8198, -5.1052, "GB", "town"),
    "amsterdam": ("Amsterdam", 52.3676, 4.9041, "NL", "city"),
    "haarlem": ("Haarlem", 52.3874, 4.6462, "NL", "town"),
    "bergen": ("Bergen", 60.3913, 5.3221, "NO", "city"),
    "flam": ("Flam", 60.8631, 7.1149, "NO", "village"),
    "vienna": ("Vienna", 48.2082, 16.3738, "AT", "city"),
    "hallstatt": ("Hallstatt", 47.5622, 13.6493, "AT", "village"),
}


@dataclass
class Trip:
    title: str
    start: int
    nights: int
    stays: list[tuple[str, int, int, str | None, int]]
    people: int = 1
    companions: list[str] = field(default_factory=list)
    summary: str | None = None
    status: str = "confirmed"
    budget: str | None = None
    tags: list[str] = field(default_factory=list)
    legs: list[tuple[str, str, str, int, str | None, str | None]] = field(default_factory=list)
    visits: list[tuple[str, int, int, str]] = field(default_factory=list)
    spending: list[tuple[str, str, str, int, int | None]] = field(default_factory=list)
    diary: list[tuple[int, str]] = field(default_factory=list)
    memo: list[tuple[str, str, str]] = field(default_factory=list)
    packing: list[tuple[str, bool]] = field(default_factory=list)
    todo: list[tuple[str, bool]] = field(default_factory=list)
    plan: list[tuple[int, str, str, str | None, str | None]] = field(default_factory=list)
    shared: bool = False
    paid_back: str | None = None


ALEX_TRIPS = (
    Trip(
        "Amsterdam winter weekend",
        -528,
        3,
        [("amsterdam", 0, 3, "Houseboat on the Prinsengracht", 120)],
        2,
        ["Sam"],
        "Canals in the cold, stroopwafels and one very long museum day.",
        tags=["city", "museums"],
        legs=[
            ("pamplona", "amsterdam", "plane", 0, "Nordic Wings", "NW 530"),
            ("amsterdam", "pamplona", "plane", 3, "Nordic Wings", "NW 531"),
        ],
        visits=[("haarlem", 0, 2, "Day trip by train")],
        spending=[
            ("transport", "Flights", "228", 0, 0),
            ("lodging", "Hotels", "360", 0, 1),
            ("other", "Excursions", "46", 2, 0),
        ],
        shared=True,
        paid_back="full",
    ),
    Trip(
        "Scottish Highlands",
        -190,
        6,
        [("edinburgh", 0, 2, "Georgian flat", 95), ("fortwilliam", 2, 6, "Lochside cottage", 88)],
        1,
        [],
        "A road trip with too much whisky and a lot of rain, in the best way.",
        tags=["roadtrip", "nature"],
        legs=[
            ("pamplona", "edinburgh", "plane", 0, "Nordic Wings", "NW 612"),
            ("edinburgh", "fortwilliam", "car", 2, None, None),
            ("fortwilliam", "pamplona", "plane", 6, "Nordic Wings", "NW 615"),
        ],
        visits=[("fortwilliam", 1, 4, "Glenfinnan viaduct and Ben Nevis views")],
        spending=[
            ("transport", "Flights", "276", 0, None),
            ("transport", "Car", "310", 2, None),
            ("lodging", "Hotels", "540", 0, None),
        ],
        diary=[(4, "Rain, then sun, then rain. The viaduct was worth every minute.")],
    ),
    Trip(
        "Andalusia road trip",
        -505,
        7,
        [("seville", 0, 3, "Casa Azahar", 90), ("cordoba", 3, 4, "Patio hotel", 70)]
        + [("granada", 4, 7, "Cave house in the Albaicin", 85)],
        2,
        ["Sam"],
        "Seven days between orange trees, patios and a very slow Alhambra queue.",
        tags=["roadtrip", "culture"],
        legs=[
            ("pamplona", "seville", "car", 0, None, None),
            ("seville", "cordoba", "car", 3, None, None),
            ("cordoba", "granada", "car", 4, None, None),
            ("granada", "pamplona", "car", 7, None, None),
        ],
        visits=[
            ("seville", 0, 1, "Real Alcazar before the heat"),
            ("cordoba", 1, 3, "The Mezquita at opening time"),
            ("granada", 2, 5, "Alhambra, evening slot"),
        ],
        spending=[
            ("lodging", "Hotels", "640", 0, 0),
            ("transport", "Fuel and parking", "210", 1, 0),
            ("other", "Excursions", "88", 5, 1),
            ("other", "Tapas crawl", "64", 2, 1),
        ],
        diary=[(1, "Seville smells of orange blossom even in autumn. Tapas until midnight.")],
        shared=True,
        paid_back="full",
    ),
    Trip(
        "Pyrenees hiking",
        -335,
        3,
        [("isaba", 0, 1, "Mountain refuge", 40), ("torla", 1, 3, "Valley guesthouse", 55)],
        1,
        [],
        "Three days of switchbacks and a lot of cheese.",
        tags=["hiking"],
        legs=[
            ("pamplona", "isaba", "car", 0, None, None),
            ("torla", "pamplona", "car", 3, None, None),
        ],
        visits=[("torla", 1, 2, "Ordesa canyon loop")],
        spending=[
            ("lodging", "Hotels", "190", 0, None),
            ("transport", "Fuel and parking", "46", 1, None),
        ],
    ),
    Trip(
        "Rome in spring",
        -400,
        4,
        [("rome", 0, 3, "Trastevere flat", 120), ("tivoli", 3, 4, None, 0)],
        2,
        ["Sam"],
        "Pasta, ruins and one memorable thunderstorm.",
        tags=["city", "food"],
        legs=[
            ("pamplona", "rome", "plane", 0, "Skyline Air", "SK 4418"),
            ("rome", "pamplona", "plane", 4, "Skyline Air", "SK 4421"),
        ],
        visits=[
            ("rome", 0, 1, "Pantheon and the old centre"),
            ("tivoli", 1, 3, "Villa d'Este gardens"),
        ],
        spending=[
            ("transport", "Flights", "310", 0, 0),
            ("lodging", "Apartment", "480", 0, 1),
            ("other", "Excursions", "56", 3, 0),
        ],
        diary=[(1, "Cacio e pepe twice in one day. No regrets.")],
        shared=True,
        paid_back="part",
    ),
    Trip(
        "Berlin tech week",
        -255,
        3,
        [("berlin", 0, 3, "Hotel near Ostbahnhof", 110)],
        1,
        [],
        "Conference days, then one free afternoon at the museums.",
        tags=["work"],
        legs=[
            ("pamplona", "berlin", "plane", 0, "Nordic Wings", "NW 220"),
            ("berlin", "pamplona", "plane", 3, "Nordic Wings", "NW 221"),
        ],
        spending=[("transport", "Flights", "196", 0, None), ("lodging", "Hotel", "330", 0, None)],
    ),
    Trip(
        "Flanders in September",
        -62,
        4,
        [
            ("bruges", 0, 2, "A small hotel by the canal", 90),
            ("ghent", 2, 4, "Loft on the Graslei", 100),
        ],
        2,
        ["Sam"],
        "Four nights of canals, belfries and too many waffles.",
        tags=["getaway"],
        legs=[
            ("pamplona", "bruges", "plane", 0, "Skyline Air", "SK 112"),
            ("bruges", "ghent", "train", 2, None, None),
            ("ghent", "pamplona", "plane", 4, "Skyline Air", "SK 113"),
        ],
        visits=[("damme", 0, 1, "By bike along the canal")],
        spending=[
            ("transport", "Flights", "268", 0, 0),
            ("lodging", "Hotel", "360", 0, 1),
            ("transport", "Train", "18", 2, 0),
            ("other", "Excursions", "42", 1, 1),
            ("other", "Beer tasting", "58", 3, 0),
        ],
        diary=[
            (1, "Rented bikes and followed the canal to Damme. Sam navigated, badly."),
            (3, "Ghent at night is the best surprise of the trip."),
        ],
        memo=[
            ("tips", "Belfry tickets", "Book the Bruges belfry before 10:00 to dodge the queue.")
        ],
        shared=True,
    ),
    Trip(
        "Copenhagen long weekend",
        -1,
        4,
        [("copenhagen", 0, 4, "Canal-side apartment", 135)],
        2,
        ["Sam"],
        "Design, cycling and cinnamon buns, with a day trip to Roskilde.",
        tags=["city", "design"],
        legs=[
            ("pamplona", "copenhagen", "plane", 0, "Nordic Wings", "NW 744"),
            ("copenhagen", "pamplona", "plane", 4, "Nordic Wings", "NW 745"),
        ],
        visits=[("roskilde", 0, 2, "Viking ship museum")],
        spending=[
            ("transport", "Flights", "342", 0, 0),
            ("lodging", "Apartment", "540", 0, 1),
            ("other", "Cash", "60", 1, 0),
        ],
        diary=[(0, "Landed late, walked the harbour with a hot dog in hand.")],
        packing=[
            ("Passport", True),
            ("Warm layers", True),
            ("Camera", False),
            ("Power adapter", True),
        ],
        todo=[("Book the Roskilde train", True), ("Dinner reservation for Saturday", False)],
        plan=[
            (1, "Breakfast at the bakery on the corner", "meal", "09:00", "10:00"),
            (1, "Rent bikes", "activity", "10:30", "11:00"),
            (2, "Day trip to Roskilde", "transport", "09:30", None),
            (2, "Viking ship museum", "activity", "11:00", "13:00"),
            (3, "Free morning", "free_time", None, None),
        ],
        shared=True,
    ),
    Trip(
        "A long weekend in Lisbon",
        30,
        3,
        [("lisbon", 0, 3, "Hotel in Alfama", 95)],
        2,
        ["Sam"],
        "Tram 28, pasteis and a sunset at the miradouro.",
        status="plan",
        budget="450",
        tags=["city"],
        legs=[
            ("pamplona", "lisbon", "plane", 0, "Skyline Air", "SK 602"),
            ("lisbon", "pamplona", "plane", 3, "Skyline Air", "SK 603"),
        ],
        visits=[("sintra", 0, 2, "Pena palace if the weather holds")],
        packing=[("Comfortable shoes", False), ("Sunglasses", False)],
        todo=[("Book flights", True), ("Reserve the fado night", False)],
        plan=[
            (1, "Pasteis de nata tour", "meal", "10:00", None),
            (2, "Sintra day trip", "activity", "09:00", None),
        ],
        shared=True,
    ),
    Trip(
        "Winter in the Dolomites",
        78,
        5,
        [
            ("bolzano", 0, 2, "Hotel in the old town", 80),
            ("ortisei", 2, 5, "Chalet with a sauna", 140),
        ],
        2,
        ["Sam"],
        "Ski days, mulled wine and a sauna every evening.",
        status="plan",
        budget="1400",
        tags=["snow"],
        todo=[("Check the ski pass prices", False), ("Rent a car with winter tyres", False)],
        shared=True,
    ),
)

SAM_TRIPS = (
    Trip(
        "Marrakech and the coast",
        -435,
        6,
        [("marrakech", 0, 4, "Riad Jasmine", 70), ("essaouira", 4, 6, "Sea-view guesthouse", 50)],
        2,
        ["Lucia"],
        "Souks, a hammam and the windiest beach.",
        tags=["culture"],
        legs=[
            ("pamplona", "marrakech", "plane", 0, "Atlas Air", "AA 310"),
            ("marrakech", "essaouira", "bus", 4, None, None),
            ("essaouira", "pamplona", "plane", 6, "Atlas Air", "AA 311"),
        ],
        visits=[("marrakech", 0, 1, "Jardin Majorelle early")],
        spending=[("transport", "Flights", "240", 0, None), ("lodging", "Hotels", "420", 0, None)],
        diary=[(2, "Bargained for a lamp and ended up with three.")],
    ),
    Trip(
        "Paris for Marta's birthday",
        -212,
        3,
        [("paris", 0, 3, "Flat in the Marais", 130)],
        4,
        ["Marta", "Lucia", "Iker"],
        "A surprise weekend: croissants, a Seine cruise and too many photos.",
        tags=["friends", "city"],
        legs=[
            ("pamplona", "paris", "train", 0, "Rail Europe", None),
            ("paris", "pamplona", "train", 3, "Rail Europe", None),
        ],
        visits=[("versailles", 0, 2, "Gardens and the fountains show")],
        spending=[("lodging", "Apartment", "390", 0, None), ("transport", "Train", "220", 0, None)],
        diary=[(1, "Marta cried at the cake. Mission accomplished.")],
    ),
    Trip(
        "Tenerife in July",
        -170,
        7,
        [("tenerife", 0, 4, "Beach apartment", 75), ("teide", 4, 7, "Mountain cabin", 60)],
        2,
        ["Lucia"],
        "Black sand, volcano sunrise and way too much papas arrugadas.",
        tags=["beach", "nature"],
        legs=[
            ("pamplona", "tenerife", "plane", 0, "Island Jet", "IJ 902"),
            ("tenerife", "pamplona", "plane", 7, "Island Jet", "IJ 903"),
        ],
        visits=[("teide", 1, 5, "Sunrise at the summit cable car")],
        spending=[
            ("transport", "Flights", "280", 0, None),
            ("transport", "Car", "190", 0, None),
            ("lodging", "Apartment", "430", 0, None),
        ],
    ),
    Trip(
        "Porto with friends",
        -120,
        2,
        [("porto", 0, 2, "A flat in Ribeira", 47)],
        3,
        ["Marta", "Iker"],
        "Port wine cellars, pastel de nata and a rain jacket that did its job.",
        tags=["friends"],
        legs=[
            ("pamplona", "porto", "plane", 0, "Skyline Air", "SK 810"),
            ("porto", "pamplona", "plane", 2, "Skyline Air", "SK 811"),
        ],
        spending=[("lodging", "Apartment", "95", 0, None)],
    ),
    Trip(
        "Prague weekend",
        14,
        3,
        [("prague", 0, 3, "Hotel by the Vltava", 88)],
        2,
        ["Lucia"],
        "Old town, jazz clubs and a day at Kutna Hora.",
        status="plan",
        budget="520",
        legs=[
            ("pamplona", "prague", "plane", 0, "Atlas Air", "AA 551"),
            ("prague", "pamplona", "plane", 3, "Atlas Air", "AA 552"),
        ],
        visits=[("kutna", 0, 2, "The bone chapel")],
        packing=[("Passport", False), ("Rain jacket", False)],
    ),
)

IDEAS_ALEX = (
    (
        "Norway fjords",
        "Ferries, waterfalls and the Flam railway.",
        "1800",
        7,
        10,
        [6, 7, 8],
        ["nature"],
        ("bergen", "flam"),
    ),
    (
        "Vienna and Hallstatt at Christmas",
        "Markets, concerts and a lake village in the snow.",
        "900",
        5,
        6,
        [12],
        ["winter"],
        ("vienna", "hallstatt"),
    ),
)
IDEAS_SAM = (
    (
        "Japan in autumn",
        "The maples, ramen and a night in a ryokan.",
        "2500",
        12,
        16,
        [10, 11],
        ["far"],
        ("kyoto", "nara"),
    ),
    (
        "Iceland ring road",
        "Waterfalls, black beaches and the northern lights.",
        "2100",
        8,
        10,
        [9, 10],
        ["nature"],
        ("reykjavik", "vik"),
    ),
    (
        "Machu Picchu",
        "The Sacred Valley and the Inca trail.",
        "3200",
        12,
        15,
        [5, 6, 9],
        ["far"],
        ("cusco",),
    ),
)


def _day(today: date, offset: int) -> date:
    return today + timedelta(days=offset)


def _clock(text: str | None) -> time | None:
    return time.fromisoformat(text) if text else None


async def _place(connection: AsyncConnection, cache: dict[str, str], key: str) -> str:
    if key not in cache:
        name, lat, lon, country, kind = CITIES[key]
        cache[key] = (
            await save_place(
                connection, PlaceIn(name=name, lat=lat, lon=lon, country_code=country, kind=kind)
            )
        ).id
    return cache[key]


async def _build(
    connection: AsyncConnection, today: date, cache: dict[str, str], one: Trip, space: str
) -> None:
    start = _day(today, one.start)
    made = await travel.create_trip(
        connection,
        travel.TripIn(
            title=one.title,
            starts_on=start,
            ends_on=start + timedelta(days=one.nights),
            travellers=one.people,
            companions=one.companions,
            tags=one.tags,
            summary=one.summary,
            status=one.status,
            budget_eur=Decimal(one.budget) if one.budget else None,
        ),
    )
    trip_id = made.id
    stay_ids = []
    for place, arrive, leave, where, _ in one.stays:
        found = await travel.add_stay(
            connection,
            trip_id,
            travel.StayIn(
                place_id=await _place(connection, cache, place),
                arrives_on=start + timedelta(days=arrive),
                leaves_on=start + timedelta(days=leave),
                accommodation=where,
            ),
        )
        stay_ids.append(found.stays[-1].id)
    for origin, goal, mode, offset, carrier, number in one.legs:
        await travel.add_leg(
            connection,
            trip_id,
            travel.LegIn(
                from_place_id=await _place(connection, cache, origin),
                to_place_id=await _place(connection, cache, goal),
                mode=mode,
                travelled_on=start + timedelta(days=offset),
                carrier=carrier,
                number=number,
            ),
        )
    for place, stay, offset, note in one.visits:
        await travel.add_visit(
            connection,
            trip_id,
            travel.VisitIn(
                place_id=await _place(connection, cache, place),
                stay_id=stay_ids[min(stay, len(stay_ids) - 1)],
                visited_on=start + timedelta(days=offset),
                note=note,
            ),
        )
    if one.shared:
        await travel.share_trip(connection, trip_id, space)
        for person in await money.ensure_travellers(connection, trip_id):
            if person.name == "Sam":
                await money.update_traveller(
                    connection,
                    trip_id,
                    person.id,
                    money.TravellerChange(member_user_id=SAM),
                    {space: {str(SAM)}},
                )
    people = await money.ensure_travellers(connection, trip_id)
    for category, concept, amount, offset, payer in one.spending:
        await travel.add_expense(
            connection,
            trip_id,
            travel.ExpenseIn(
                category=category,
                concept=concept,
                amount_eur=Decimal(amount),
                spent_on=start + timedelta(days=min(offset, one.nights)),
                paid_by=people[payer].id if payer is not None and payer < len(people) else None,
            ),
        )
    if one.paid_back and len(people) > 1:
        balance = await money.balance(connection, trip_id)
        for debt in balance.transfers:
            share = Decimal(debt.amount_eur)
            if one.paid_back == "part":
                share = (share / 2).quantize(Decimal("0.01"))
            await money.settle(
                connection,
                trip_id,
                money.SettlementIn(
                    from_traveller=debt.from_traveller.id,
                    to_traveller=debt.to_traveller.id,
                    amount_eur=share,
                    settled_on=_day(today, min(one.start + one.nights + 3, -1)),
                ),
            )
    for offset, body in one.diary:
        await journal.write(
            connection,
            trip_id,
            start + timedelta(days=offset),
            journal.JournalIn(body=body),
        )
    for category, title, body in one.memo:
        await notes.add_note(
            connection, trip_id, notes.NoteIn(category=category, title=title, body=body)
        )
    for kind, items in (("packing", one.packing), ("todo", one.todo)):
        for text_, done in items:
            found = await lists.add_items(
                connection, trip_id, [lists.ItemIn(list=kind, text=text_)]
            )
            if done:
                wanted = next(one for one in found if one.text == text_)
                await lists.change_item(
                    connection, trip_id, wanted.id, lists.ItemChange(checked=True)
                )
    for offset, title, kind, begins, ends in one.plan:
        await itinerary.add_block(
            connection,
            trip_id,
            itinerary.BlockIn(
                day=start + timedelta(days=offset),
                kind=kind,
                title=title,
                starts_at=_clock(begins),
                ends_at=_clock(ends),
            ),
        )


async def _ideas(
    connection: AsyncConnection, cache: dict[str, str], rows: tuple, space: str | None
) -> None:
    have = {one.title for one in await ideas.ideas(connection)}
    for title, notes_, budget, low, high, months, tags, places in rows:
        if title in have:
            continue
        made = await ideas.create_idea(
            connection,
            ideas.IdeaIn(
                title=title,
                notes=notes_,
                budget_eur=Decimal(budget),
                days_min=low,
                days_max=high,
                months=months,
                tags=tags,
            ),
        )
        for key in places:
            await ideas.add_place(connection, made.id, await _place(connection, cache, key), None)
        if space and title.startswith("Norway"):
            await ideas.share_idea(connection, made.id, space)


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    space = str(current_spaces.get()[0])
    cache: dict[str, str] = {}
    have = {one.title for one in await travel.all_trips(connection)}
    mine = ALEX_TRIPS if persona.key == "alex" else SAM_TRIPS
    for one in mine:
        if one.title not in have:
            await _build(connection, today, cache, one, space)
    await _ideas(connection, cache, IDEAS_ALEX if persona.key == "alex" else IDEAS_SAM, space)
