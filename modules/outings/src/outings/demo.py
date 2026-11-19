from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from arga_tenancy import current_spaces
from outings import agenda, by_hand, explore, profile

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-0000000a7e5d")

WISH = text("""
    insert into outings.outings_wish
        (id, kind, name, body, place_name, place_town, place_country, done_at, created_at, space_id)
    values (:id, :kind, :name, :body, :place, :town, :country, :done_at, :created_at, :space_id)
    on conflict (id) do nothing
""")


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.key}:{key}")


COORDS = {
    "Pamplona": (42.8125, -1.6458),
    "Burlada": (42.8211, -1.6044),
    "Villava": (42.8317, -1.6086),
    "Huarte": (42.8206, -1.5897),
    "Baranain": (42.7993, -1.6717),
    "Zizur Mayor": (42.7861, -1.6711),
    "Tudela": (42.1315, -1.6072),
    "Estella": (42.6719, -2.0314),
    "Tafalla": (42.5278, -1.6742),
    "Olite": (42.4817, -1.6503),
    "Sanguesa": (42.5726, -1.2819),
    "Elizondo": (43.1469, -1.5159),
    "Lodosa": (42.4279, -2.0866),
}
UPDATE_WISH = text("""
    update outings.outings_wish set lat = :lat, lon = :lon, place_name = :venue
    where id = :id
""")
VENUE = text("""
    insert into outings.outings_venue (name, town, lat, lon, found)
    values (:name, :town, :lat, :lon, true)
    on conflict (user_id, name, town) do nothing
""")


def _where(town: str | None, index: int) -> tuple[float, float] | None:
    if town not in COORDS:
        return None
    lat, lon = COORDS[town]
    return lat + (index % 5 - 2) * 0.0021, lon + (index % 3 - 1) * 0.0027


def _wishes(persona: Persona, area: profile.Profile) -> list[dict[str, Any]]:
    far = area.region.towns
    here = "Pamplona"
    common = [
        ("tapas", "eat", "Tapas crawl in the old town", "Go early.", here, "Calle San Nicolas"),
        ("hill", "plan", "Climb the hill above town at sunset", None, "Huarte", "Monte Ezkaba"),
        (
            "forest",
            "getaway",
            "Beech forest in autumn",
            "Go when the leaves turn red.",
            "Elizondo",
            "Baztan valley",
        ),
        ("japan", "trip", "Japan", "Cherry blossom season, two weeks.", None, None),
        ("ciudadela", "plan", "Evening walk around the Ciudadela", None, here, "La Ciudadela"),
        (
            "olite",
            "getaway",
            "Medieval weekend in Olite",
            "Castle and the wine route.",
            "Olite",
            "Palacio Real",
        ),
    ]
    own = {
        "alex": [
            (
                "ramen",
                "eat",
                "The new ramen place",
                "Someone at work recommended it.",
                here,
                "Ramen Kioto",
            ),
            ("castle", "getaway", "Castle town for a weekend", None, far[1], None),
            ("lisbon", "trip", "Lisbon by train", None, None, None),
            (
                "vermouth",
                "eat",
                "Vermouth hour on the Castle Square",
                None,
                here,
                "Bar Torino",
            ),
            (
                "kayak",
                "plan",
                "Kayak on the Arga",
                "Ask Iker about the rental.",
                "Burlada",
                "Parque Fluvial",
            ),
            (
                "norway",
                "trip",
                "Norway fjords by ferry",
                "Bergen to Flam.",
                None,
                None,
            ),
            (
                "sunrise",
                "plan",
                "Sunrise from the Perdon ridge",
                None,
                "Zizur Mayor",
                "Perdon summit",
            ),
        ],
        "sam": [
            ("market", "plan", "Saturday farmers' market", None, here, "Plaza Santo Domingo"),
            (
                "caves",
                "getaway",
                "Caves and a long lunch",
                "Book the tour ahead.",
                "Sanguesa",
                "Bodega Valle",
            ),
            ("iceland", "trip", "Iceland in winter", "Northern lights.", None, None),
            (
                "bakery",
                "eat",
                "Sourdough bakery everyone raves about",
                None,
                "Villava",
                "Panaderia Irati",
            ),
            (
                "pottery",
                "plan",
                "Pottery workshop for beginners",
                None,
                "Baranain",
                "Taller Arcilla",
            ),
            (
                "tudela",
                "getaway",
                "Vegetable fair weekend in Tudela",
                "Menestra!",
                "Tudela",
                "Charter Square",
            ),
            ("peru", "trip", "Peru and Machu Picchu", "Save for 2027.", None, None),
        ],
    }.get(persona.key, [])
    done = {
        "alex": [
            ("river", "plan", "Walk along the river", "Burlada", 40, "Parque Fluvial"),
            ("pintxos", "eat", "Pintxo night with the team", "Pamplona", 95, "Bar Gaucho"),
            ("estella", "getaway", "Day in Estella", "Estella", 170, "Casco Viejo"),
            ("balloon", "plan", "Hot air balloon festival", "Estella", 260, None),
            ("steak", "eat", "Txuleta at the cider house", "Elizondo", 380, "Sidreria Eguzki"),
        ],
        "sam": [
            ("wine", "getaway", "Wine harvest weekend", far[3], 300, "Bodega Vinedos Altos"),
            ("brunch", "eat", "Brunch with Marta", "Pamplona", 28, "Cafe Jardin"),
            (
                "lantern",
                "plan",
                "Lantern festival at the park",
                "Pamplona",
                110,
                "Parque Yamaguchi",
            ),
            ("olive", "getaway", "Olive oil mill visit", "Tafalla", 210, "Almazara Tafallesa"),
            ("opera", "plan", "Opera night at Baluarte", "Pamplona", 420, "Baluarte"),
        ],
    }.get(persona.key, [])
    out = [
        {"key": k, "kind": kind, "name": name, "body": body, "town": town, "venue": venue,
         "days": None}
        for k, kind, name, body, town, venue in [*common, *own]
    ]  # fmt: skip
    out += [
        {"key": k, "kind": kind, "name": name, "body": None, "town": town, "venue": venue,
         "days": days}
        for k, kind, name, town, days, venue in [
            *done,
            ("museum", "plan", "Museum night", "Pamplona", 520, "Museo de Navarra"),
        ]
    ]  # fmt: skip
    return out


def _events(area: profile.Profile, today: date) -> list[tuple[by_hand.EventIn, str | None]]:
    plan = [
        ("Jazz in the square", "stage", "Pamplona", "Castle Square", 2, 0, "21:00", False),
        ("Farmers' market", "festival", "Pamplona", "Plaza Santo Domingo", 3, 0, "10:00", False),
        ("Food week", "eat", "Burlada", "Various bars", 6, 6, None, True),
        ("Photography exhibition", "culture", "Pamplona", "Museo de Navarra", 1, 40, None, False),
        ("Town fiestas", "festival", "Estella", "Charter Square", 12, 4, None, True),
        (
            "Mountain trail race",
            "outdoors",
            "Elizondo",
            "Fronton de Elizondo",
            20,
            0,
            "09:00",
            False,
        ),
        ("Open-air cinema", "stage", "Villava", "Parque de la Atarrabia", 9, 0, "22:00", False),
        ("Harvest fair", "eat", "Tafalla", "Plaza de Navarra", 35, 1, None, True),
        ("Christmas market", "festival", "Pamplona", "Paseo Sarasate", 24, 30, "11:00", True),
        ("Orchestra: Beethoven nights", "stage", "Pamplona", "Baluarte", 5, 0, "20:00", False),
        ("Pintxo contest", "eat", "Pamplona", "Calle Estafeta", 8, 3, None, False),
        ("Craft fair", "culture", "Olite", "Plaza Carlos III", 11, 1, "10:00", False),
        ("Choir evening", "stage", "Huarte", "Iglesia de San Esteban", 7, 0, "19:30", False),
        (
            "Guided walk: the walls",
            "outdoors",
            "Pamplona",
            "Portal de Francia",
            4,
            0,
            "11:00",
            False,
        ),
        ("Mushroom day", "eat", "Sanguesa", "Casa de Cultura", 16, 0, "12:00", False),
        ("Stand-up night", "stage", "Zizur Mayor", "Auditorio", 10, 0, "21:30", False),
        ("Winter light festival", "culture", "Tudela", "Casco Antiguo", 28, 10, "18:00", True),
        ("Neighbourhood fiestas", "festival", "Baranain", "Plaza Consistorial", -6, 3, None, False),
        ("Wine fair", "eat", "Lodosa", "Bodegas Ribera", -14, 2, None, False),
        ("Chestnut roast", "eat", "Pamplona", "Parque de la Taconera", -3, 0, "17:00", False),
        ("Contemporary dance", "stage", "Pamplona", "Teatro Gayarre", -9, 0, "20:00", False),
    ]
    return [
        (
            by_hand.EventIn(
                title=title,
                category=category,
                town=town,
                venue=venue,
                starts_on=today + timedelta(days=start),
                ends_on=today + timedelta(days=start + length),
                time=clock,
                highlight=big,
                summary=f"{title} in {town}.",
                link=f"https://agenda.example/demo/{start}-{n}",
            ),
            venue,
        )
        for n, (title, category, town, venue, start, length, clock, big) in enumerate(plan)
    ]


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    area = profile.load(profile.resolve(persona.area))
    zone = ZoneInfo(persona.timezone)
    space = next(iter(current_spaces.get()), None)
    for one in _wishes(persona, area):
        moment = None
        if one["days"] is not None:
            moment = datetime.combine(today - timedelta(days=one["days"]), time(18), zone)
        shared = one["key"] in ("forest", "japan") and persona.key == "alex"
        await connection.execute(
            WISH,
            {
                "id": _id(persona, one["key"]),
                "kind": one["kind"],
                "name": one["name"],
                "body": one["body"],
                "place": one["venue"] or one["town"],
                "town": one["town"],
                "country": area.country if one["town"] else None,
                "done_at": moment,
                "created_at": moment or datetime.combine(today, time(9), zone),
                "space_id": space if shared else None,
            },
        )
        spot = _where(one["town"], len(one["key"]))
        if spot:
            await connection.execute(
                UPDATE_WISH,
                {
                    "id": _id(persona, one["key"]),
                    "lat": spot[0],
                    "lon": spot[1],
                    "venue": one["venue"] or one["town"],
                },
            )
    for kind, term in (
        ("like", "jazz"),
        ("like", "market"),
        ("like", "pintxo"),
        ("like", "choir"),
        ("mute", "conference"),
        ("mute", "bingo"),
    ):
        await explore.add_interest(connection, explore.InterestIn(kind=kind, term=term))
    planned = _events(area, today)
    added = await by_hand.add(connection, [one for one, _ in planned])
    for index, (_, venue) in enumerate(planned):
        town = planned[index][0].town or ""
        spot = _where(town, index)
        if venue and spot:
            await connection.execute(
                VENUE, {"name": venue, "town": town, "lat": spot[0], "lon": spot[1]}
            )
    ids = [one.event_id for one in added if one.event_id]
    for position in (0, 1, 5, 9, 12):
        if position < len(ids):
            await agenda.save(connection, ids[position])
    for position in (0, 9):
        if position < len(ids):
            await agenda.to_calendar(connection, ids[position], True)
