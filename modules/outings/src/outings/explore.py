from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from outings import agenda
from outings.common import Conflict, NotFound, today

When = Literal["weekend", "week", "month", "quarter", "year"]
Zone = Literal["pamplona", "navarra"]
Sort = Literal["best", "date"]

DAYS = {"week": 6, "month": 30, "quarter": 91, "year": 365}

PAMPLONA = 3
HIGHLIGHT = 3
LIKED = 4
YOURS = 1


def window(when: When, day: date | None = None) -> tuple[date, date]:
    day = day or today()
    if when == "weekend":
        return agenda.window("weekend", day)
    return day, day + timedelta(days=DAYS[when])


def matches(event: agenda.Event, query: str) -> bool:
    words = agenda.fold(query).split()
    if not words:
        return True
    hay = agenda.haystack(event)
    return all(f" {word}" in hay for word in words)


def score(event: agenda.Event, liked: list[str]) -> int:
    points = 0
    if event.zone == "pamplona":
        points += PAMPLONA
    if event.highlight:
        points += HIGHLIGHT
    if liked and agenda.mentions(event, liked):
        points += LIKED
    if event.in_calendar or event.wish_id:
        points += YOURS
    return points


MADRID = ZoneInfo("Europe/Madrid")


class Found(BaseModel):
    first: date
    last: date
    total: int
    events: list[agenda.Event]


LIKED_TERMS = text("select folded from outings.outings_interest where kind = 'like'")


async def search(
    connection: AsyncConnection,
    query: str | None = None,
    when: When = "quarter",
    first: date | None = None,
    last: date | None = None,
    zone: Zone | None = None,
    category: str | None = None,
    sort: Sort = "date",
    limit: int = 40,
    offset: int = 0,
    town: str | None = None,
    since: date | None = None,
) -> Found:
    if first is None or last is None:
        first, last = window(when)
    found = await agenda.events(connection, first, last, category, town)
    if zone:
        found = [one for one in found if one.zone == zone]
    if since:
        found = [one for one in found if one.first_seen.astimezone(MADRID).date() >= since]
    if query and query.strip():
        found = [one for one in found if matches(one, query)]
    if sort == "best":
        liked = [row.folded for row in await connection.execute(LIKED_TERMS)]
        found.sort(key=lambda one: (-score(one, liked), one.starts_on, one.title.casefold()))
    return Found(first=first, last=last, total=len(found), events=found[offset : offset + limit])


async def mine(connection: AsyncConnection, first: date, last: date) -> list[agenda.Event]:
    found = await agenda.events(connection, first, last, everything=True)
    return [one for one in found if one.in_calendar or one.wish_id]


async def dismiss(connection: AsyncConnection, event_id: str, on: bool = True) -> agenda.Event:
    updated = await connection.execute(
        text("""
            update outings.outings_event
            set dismissed_at = case when :on then coalesce(dismissed_at, now()) end,
                updated_at = now()
            where id = cast(:id as uuid)
        """),
        {"id": event_id, "on": on},
    )
    if updated.rowcount == 0:
        raise NotFound(f"evento {event_id}")
    return await agenda.event(connection, event_id)


class Interest(BaseModel):
    id: str
    kind: Literal["like", "mute"]
    term: str


class InterestIn(BaseModel):
    kind: Literal["like", "mute"]
    term: Annotated[str, Field(min_length=2, max_length=80)]


async def interests(connection: AsyncConnection) -> list[Interest]:
    rows = await connection.execute(
        text("""
            select id::text as id, kind, term from outings.outings_interest
            order by kind, lower(term)
        """)
    )
    return [Interest(id=row.id, kind=row.kind, term=row.term) for row in rows]


async def add_interest(connection: AsyncConnection, given: InterestIn) -> Interest:
    term = " ".join(given.term.split())
    folded = agenda.fold(term)
    if len(folded) < 2:
        raise Conflict("eso no tiene letras que buscar", "INVALID")
    row = (
        await connection.execute(
            text("""
                insert into outings.outings_interest (kind, term, folded)
                values (:kind, :term, :folded)
                on conflict (user_id, kind, folded) do update set term = excluded.term
                returning id::text as id, kind, term
            """),
            {"kind": given.kind, "term": term, "folded": folded[:80]},
        )
    ).one()
    return Interest(id=row.id, kind=row.kind, term=row.term)


async def remove_interest(connection: AsyncConnection, interest_id: str) -> Interest:
    row = (
        await connection.execute(
            text("""
                delete from outings.outings_interest where id = cast(:id as uuid)
                returning id::text as id, kind, term
            """),
            {"id": interest_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(f"interés {interest_id}")
    return Interest(id=row.id, kind=row.kind, term=row.term)
