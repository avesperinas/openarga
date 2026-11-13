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


def _wishes(persona: Persona, area: profile.Profile) -> list[dict[str, Any]]:
    near, far = area.near.towns, area.region.towns
    common = [
        (
            "tapas",
            "eat",
            "Tapas crawl in the old town",
            "Go early.",
            near[0],
        ),
        ("hill", "plan", "Climb the hill above town at sunset", None, near[1]),
        ("forest", "getaway", "Beech forest in autumn", "Go when the leaves turn red.", far[0]),
        ("japan", "trip", "Japan", "Cherry blossom season, two weeks.", None),
    ]
    own = {
        "alex": [
            ("ramen", "eat", "The new ramen place", "Someone at work recommended it.", near[0]),
            ("castle", "getaway", "Castle town for a weekend", None, far[1]),
            ("lisbon", "trip", "Lisbon by train", None, None),
        ],
        "sam": [
            ("market", "plan", "Saturday farmers' market", None, near[0]),
            ("caves", "getaway", "Caves and a long lunch", "Book the tour ahead.", far[2]),
            ("iceland", "trip", "Iceland in winter", "Northern lights.", None),
        ],
    }.get(persona.key, [])
    done = {
        "alex": [("river", "plan", "Walk along the river", near[0], 40)],
        "sam": [("wine", "getaway", "Wine harvest weekend", far[3], 300)],
    }.get(persona.key, [])
    out = [
        {"key": key, "kind": kind, "name": name, "body": body, "town": town, "days": None}
        for key, kind, name, body, town in [*common, *own]
    ]
    out += [
        {"key": key, "kind": kind, "name": name, "body": None, "town": town, "days": days}
        for key, kind, name, town, days in [*done, ("museum", "plan", "Museum night", near[0], 520)]
    ]
    return out


def _events(area: profile.Profile, today: date) -> list[by_hand.EventIn]:
    near, far = area.near.towns, area.region.towns
    plan = [
        ("Jazz in the square", "stage", near[0], 2, 0, "21:00", False),
        ("Farmers' market", "festival", near[0], 3, 0, "10:00", False),
        ("Food week", "eat", near[1], 6, 6, None, True),
        ("Photography exhibition", "culture", near[0], 1, 40, None, False),
        ("Town fiestas", "festival", far[0], 12, 4, None, True),
        ("Mountain trail race", "outdoors", far[1], 20, 0, "09:00", False),
        ("Open-air cinema", "stage", near[2], 9, 0, "22:00", False),
        ("Harvest fair", "eat", far[2], 35, 1, None, True),
    ]
    return [
        by_hand.EventIn(
            title=title,
            category=category,
            town=town,
            starts_on=today + timedelta(days=start),
            ends_on=today + timedelta(days=start + length),
            time=clock,
            highlight=big,
            summary=f"A synthetic {category} event for the demo.",
            link=f"https://agenda.example/demo/{start}",
        )
        for title, category, town, start, length, clock, big in plan
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
                "place": one["town"],
                "town": one["town"],
                "country": area.country if one["town"] else None,
                "done_at": moment,
                "created_at": moment or datetime.combine(today, time(9), zone),
                "space_id": space if shared else None,
            },
        )
    for kind, term in (("like", "jazz"), ("like", "market"), ("mute", "conference")):
        await explore.add_interest(connection, explore.InterestIn(kind=kind, term=term))
    added = await by_hand.add(connection, _events(area, today))
    ids = [one.event_id for one in added if one.event_id]
    if ids:
        await agenda.save(connection, ids[0])
