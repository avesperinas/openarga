from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from outings import agenda, explore, places, profile
from outings.common import today
from outings.words import say

MADRID = ZoneInfo("Europe/Madrid")
AHEAD_DAYS = 45
NEAR_KM = 5.0
NEAR = 4
HOUR = time(19, 0)
WEEKLY_CAP = 4
SHOWN = 3
NEARBY_KINDS = ("eat", "plan", "getaway")
NAME_MIN = 5


class Pick(BaseModel):
    event: agenda.Event
    reasons: list[str]
    score: int


LIKED = text("select term, folded from outings.outings_interest where kind = 'like'")
WISHES = text(f"""
    select name, lat, lon from outings.outings_wish
    where done_at is null and kind in {NEARBY_KINDS}
""")


async def picks(connection: AsyncConnection, arrived_since: datetime | None = None) -> list[Pick]:
    first = today()
    found = await agenda.events(connection, first, first + timedelta(days=AHEAD_DAYS))
    liked = [(row.term, row.folded) for row in await connection.execute(LIKED)]
    folded = [one for _, one in liked]
    wishes = [row for row in await connection.execute(WISHES)]
    out = []
    for event in found:
        if event.dismissed or event.wish_id or event.in_calendar:
            continue
        if arrived_since and event.first_seen < arrived_since:
            continue
        reasons = []
        hit = next((term for term, one in liked if agenda.mentions(event, [one])), None)
        if hit:
            reasons.append(say("reason.liked", term=hit))
        if event.highlight and event.zone == "near":
            reasons.append(say("reason.big", area=profile.current().near.name))
        wish = _near(event, wishes)
        if wish:
            reasons.append(say("reason.near_wish", wish=wish))
        if not reasons:
            continue
        score = explore.score(event, folded) + (NEAR if wish else 0)
        out.append(Pick(event=event, reasons=reasons, score=score))
    out.sort(key=lambda one: (-one.score, one.event.starts_on, one.event.title.casefold()))
    return out


def _near(event: agenda.Event, wishes: list[Any]) -> str | None:
    for wish in wishes:
        placed = event.lat is not None and event.lon is not None and wish.lat is not None
        if placed and places.km((event.lat, event.lon), (wish.lat, wish.lon)) <= NEAR_KM:
            return wish.name
        name = agenda.fold(wish.name)
        if len(name) >= NAME_MIN and agenda.mentions(event, [name]):
            return wish.name
    return None


def _when(event: agenda.Event) -> str:
    where = event.town or event.venue or ""
    first, last = event.starts_on, event.ends_on
    if last != first:
        days = say(
            "when.range",
            first_day=first.day,
            first_month=first.month,
            last_day=last.day,
            last_month=last.month,
        )
    else:
        days = say("when.one", day=first.day, month=first.month)
    return f"{where}, {days}" if where else days


def _arrived_on(event: agenda.Event) -> date:
    return event.first_seen.astimezone(MADRID).date()


HREF = "/outings/explore"


def for_you(found: list[Pick], now: date) -> list[dict[str, Any]]:
    by_day: dict[date, list[Pick]] = {}
    for one in found:
        arrived = _arrived_on(one.event)
        if now - arrived <= timedelta(days=6):
            by_day.setdefault(arrived, []).append(one)
    out = []
    for day in sorted(by_day, reverse=True)[:WEEKLY_CAP]:
        those = by_day[day]
        if len(those) == 1:
            [one] = those
            title = say("notify.for_you.one", title=one.event.title)
            body = f"{_when(one.event)}. {one.reasons[0]}."
        else:
            title = say("notify.for_you.many", count=len(those))
            body = " · ".join(one.event.title for one in those[:SHOWN])
        href = f"{HREF}?new={day.isoformat()}"
        out.append(
            notify.notification(
                "for_you", f"for_you:{day.isoformat()}", title, href, notify.at(day, HOUR), body
            )
        )
    return out


def weekend(found: list[Pick], now: date) -> list[dict[str, Any]]:
    friday, sunday = agenda.window("weekend", now)
    thursday = friday - timedelta(days=1)
    if now > friday:
        return []
    those = [one for one in found if one.event.starts_on <= sunday and one.event.ends_on >= friday]
    if not those:
        return []
    return [
        notify.notification(
            "weekend",
            f"weekend:{friday.isoformat()}",
            say("notify.weekend"),
            f"{HREF}?when=weekend",
            notify.at(thursday, HOUR),
            " · ".join(one.event.title for one in those[:SHOWN]),
        )
    ]


SAVED = text("""
    select w.id::text as id, w.name, w.starts_on, e.in_calendar
    from outings.outings_wish w
    join outings.outings_event e on e.id = w.event_id
    where w.done_at is null and w.starts_on is not null and w.starts_on >= :today
      and w.starts_on <= :until
""")


async def saved_soon(connection: AsyncConnection, now: date) -> list[dict[str, Any]]:
    out = []
    rows = await connection.execute(
        SAVED, {"today": now, "until": now + timedelta(days=AHEAD_DAYS)}
    )
    for row in rows:
        if row.in_calendar:
            continue
        eve = row.starts_on - timedelta(days=1)
        out.append(
            notify.notification(
                "saved_soon",
                f"saved:{row.id}:{row.starts_on.isoformat()}",
                say("notify.saved_soon", name=row.name),
                f"/outings/wishes/{row.id}",
                notify.at(max(eve, now), HOUR),
                say("notify.saved_soon.body"),
            )
        )
    return out


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    now = today()
    found = await picks(connection)
    return [*for_you(found, now), *weekend(found, now), *await saved_soon(connection, now)]
