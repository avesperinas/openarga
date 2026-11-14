from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from arga_tenancy import current_spaces

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-0000000b1a77")
WORKDAYS = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

LAYER = text("""
    insert into planner.planner_calendar
        (id, name, tone, display, position, days_off_from, space_id)
    values (:id, :name, :tone, :display, :position, :days_off_from, :space_id)
    on conflict (id) do nothing
""")

EVENT = text("""
    insert into planner.planner_event
        (id, calendar_id, title, all_day, start_at, end_at, start_date, end_date, tz,
         location, notes, rrule, space_id)
    values (:id, :calendar_id, :title, :all_day, :start_at, :end_at, :start_date, :end_date, :tz,
            :location, :notes, :rrule, :space_id)
    on conflict (id) do nothing
""")


@dataclass(frozen=True)
class Event:
    key: str
    layer: str
    title: str
    day: date
    start: time | None = None
    hours: float = 1
    days: int = 1
    location: str | None = None
    rrule: str | None = None


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.key}:{key}")


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _next(day: date, weekday: int) -> date:
    return day + timedelta(days=(weekday - day.weekday()) % 7 or 7)


def _events(persona: Persona, today: date) -> list[Event]:
    alex = persona.key == "alex"
    start = _monday(today) - timedelta(weeks=8)
    class_day = _monday(start) + timedelta(days=1 if alex else 0)
    return [
        Event("workday", "work", "Workday", start, time(9 if alex else 8), 8, rrule=WORKDAYS),
        Event(
            "class",
            "personal",
            "English class" if alex else "Pilates",
            class_day,
            time(19),
            rrule="FREQ=WEEKLY;BYDAY=TU,TH" if alex else "FREQ=WEEKLY;BYDAY=MO,WE",
            location="Language school" if alex else "Sports centre",
        ),
        Event("dentist", "personal", "Dentist", today + timedelta(days=3), time(16, 30)),
        Event("haircut", "personal", "Haircut", today - timedelta(days=9), time(12)),
        Event(
            "dinner",
            "personal",
            "Dinner with friends",
            _next(today, 5),
            time(21),
            2.5,
            location="Old town",
        ),
        Event("trip", "personal", "Weekend away", _next(today, 4) + timedelta(weeks=3), days=3),
        Event("festival", "local", "Town festival", today + timedelta(days=20)),
        Event("patron", "local", "Patron saint's day", today - timedelta(days=40)),
    ]


def _shared(today: date) -> list[Event]:
    return [
        Event("rent", "home", "Pay the rent", date(2020, 1, 1), rrule="FREQ=MONTHLY;BYMONTHDAY=1"),
        Event(
            "shop", "home", "Weekly shop", date(2020, 1, 4), time(10, 30), 1.5, rrule="FREQ=WEEKLY"
        ),
        Event("plumber", "home", "Plumber visit", today + timedelta(days=6), time(9), 2),
    ]


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    zone = ZoneInfo(persona.timezone)
    space = next(iter(current_spaces.get()), None)
    layers = {key: _id(persona, f"layer-{key}") for key in ("personal", "work", "local")}
    for position, (key, name, tone, display, off) in enumerate(
        (
            ("personal", "Personal", 3, "events", []),
            ("local", "Local holidays", 4, "events", []),
            ("work", "Work", 5, "background", [layers["local"]]),
        )
    ):
        await connection.execute(
            LAYER,
            {
                "id": layers[key],
                "name": name,
                "tone": tone,
                "display": display,
                "position": position,
                "days_off_from": off,
                "space_id": None,
            },
        )
    events = _events(persona, today)
    if persona.key == "alex" and space is not None:
        layers["home"] = _id(persona, "layer-home")
        await connection.execute(
            LAYER,
            {
                "id": layers["home"],
                "name": "Home",
                "tone": 7,
                "display": "events",
                "position": 3,
                "days_off_from": [],
                "space_id": space,
            },
        )
        events += _shared(today)
    for one in events:
        await connection.execute(EVENT, _row(persona, one, layers, zone, space))


def _row(
    persona: Persona, one: Event, layers: dict[str, UUID], zone: ZoneInfo, space: UUID | None
) -> dict:
    timed = one.start is not None
    start = datetime.combine(one.day, one.start, zone) if one.start else None
    return {
        "id": _id(persona, f"event-{one.key}"),
        "calendar_id": layers[one.layer],
        "title": one.title,
        "all_day": not timed,
        "start_at": start,
        "end_at": start + timedelta(hours=one.hours) if start else None,
        "start_date": None if timed else one.day,
        "end_date": None if timed else one.day + timedelta(days=one.days),
        "tz": persona.timezone,
        "location": one.location,
        "notes": None,
        "rrule": one.rrule,
        "space_id": space if one.layer == "home" else None,
    }
