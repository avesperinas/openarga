from __future__ import annotations

import os
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from planner import calendar
from planner.words import say

KINDS = {"upnext": "upnext", "calendar": "calendar", "today": "agenda", "week": "week"}
HOME_TZ = os.environ.get("PLANNER_DEFAULT_TZ", "Europe/Madrid")
UPNEXT = 5
LOOKAHEAD_DAYS = 60


def _weekday(day: date) -> str:
    return say(f"weekday.{day.weekday()}")


async def _visible(connection: AsyncConnection, *, backgrounds: bool = True) -> list[str]:
    return [
        one.id
        for one in await calendar.calendars(connection, create_default=False, subscriptions=False)
        if one.visible and (backgrounds or one.display != "background")
    ]


async def _backgrounds(connection: AsyncConnection) -> set[str]:
    return {
        one.id
        for one in await calendar.calendars(connection, create_default=False, subscriptions=False)
        if one.display == "background"
    }


async def upnext(connection: AsyncConnection, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    zone = ZoneInfo(HOME_TZ)
    visible = await _visible(connection, backgrounds=False)
    if not visible:
        return envelope(KINDS["upnext"], "empty", {"detail": say("widget.hidden")})
    found = await calendar.occurrences(
        connection, now, now + timedelta(days=LOOKAHEAD_DAYS), visible
    )
    today = now.astimezone(zone).date()
    events = []
    for one in found:
        if one.all_day:
            first = date.fromisoformat(one.start)
            if first < today:
                continue
            at = datetime.combine(first, time(), zone)
            detail = (
                say("widget.all_day")
                if first == today
                else say("widget.day_all_day", day=f"{_weekday(first)} {first.day}")
            )
        else:
            at = datetime.fromisoformat(one.start)
            if at < now:
                continue
            local = at.astimezone(zone).date()
            detail = one.location or (
                say("widget.today") if local == today else f"{_weekday(local)} {local.day}"
            )
        events.append({"at": at.isoformat(), "title": one.title, "detail": detail})
    events.sort(key=lambda e: e["at"])
    if not events:
        return envelope(
            KINDS["upnext"], "empty", {"detail": say("widget.nothing_ahead", days=LOOKAHEAD_DAYS)}
        )
    return envelope(KINDS["upnext"], "ready", {"events": events[:UPNEXT]})


async def _entries(
    connection: AsyncConnection, start: datetime, end: datetime, *, backgrounds: bool
) -> list[dict]:
    layers = {
        one.id: one
        for one in await calendar.calendars(connection, create_default=False, subscriptions=False)
        if one.visible
    }
    wanted = [one.id for one in layers.values() if backgrounds or one.display != "background"]
    if not wanted:
        return []
    found = await calendar.occurrences(connection, start, end, wanted)
    entries = []
    for one in found:
        layer = layers[one.calendar_id]
        if layer.display == "background" and not one.all_day:
            continue
        entry: dict = {"start": one.start, "end": one.end, "title": one.title}
        if one.all_day:
            entry["all_day"] = True
        if one.location:
            entry["detail"] = one.location
        if 1 <= layer.tone <= 10:
            entry["tone"] = layer.tone
        entries.append(entry)
    return entries


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time(), ZoneInfo(HOME_TZ))


async def agenda(connection: AsyncConnection, now: datetime | None = None) -> dict:
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo(HOME_TZ)).date()
    if not await _visible(connection, backgrounds=False):
        return envelope(KINDS["today"], "empty", {"detail": say("widget.hidden")})
    entries = await _entries(
        connection, _day_start(local), _day_start(local + timedelta(days=7)), backgrounds=False
    )
    return envelope(KINDS["today"], "ready", {"entries": entries})


async def week(connection: AsyncConnection, now: datetime | None = None) -> dict:
    local = (now or datetime.now(UTC)).astimezone(ZoneInfo(HOME_TZ)).date()
    if not await _visible(connection, backgrounds=False):
        return envelope(KINDS["week"], "empty", {"detail": say("widget.hidden")})
    entries = await _entries(
        connection, _day_start(local), _day_start(local + timedelta(days=7)), backgrounds=False
    )
    return envelope(KINDS["week"], "ready", {"entries": entries})


async def month(connection: AsyncConnection, now: datetime | None = None) -> dict:
    zone = ZoneInfo(HOME_TZ)
    today = (now or datetime.now(UTC)).astimezone(zone).date()
    first = today.replace(day=1)
    following = (first + timedelta(days=32)).replace(day=1)
    entries = await _entries(
        connection,
        datetime.combine(first, time(), zone),
        datetime.combine(following, time(), zone),
        backgrounds=True,
    )
    marked: set[int] = set()
    for one in entries:
        if one.get("all_day"):
            start, end = date.fromisoformat(one["start"]), date.fromisoformat(one["end"])
        else:
            start = datetime.fromisoformat(one["start"]).astimezone(zone).date()
            end = datetime.fromisoformat(one["end"]).astimezone(zone).date() + timedelta(days=1)
        day = max(start, first)
        while day < min(end, following):
            marked.add(day.day)
            day += timedelta(days=1)
    return envelope(
        KINDS["calendar"],
        "ready",
        {"marked": sorted(marked), "today": today.day, "entries": entries},
    )


RENDERERS = {"upnext": upnext, "calendar": month, "today": agenda, "week": week}
