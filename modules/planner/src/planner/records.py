from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from planner import calendar, zones
from planner.words import say

APP = "planner"
AHEAD = timedelta(days=31)

FIRST = text("""
    select min(coalesce(start_at, start_date::timestamptz)) from planner.planner_event
    where calendar_id = any(cast(:calendars as uuid[]))
""")


def _when(one: calendar.Occurrence) -> tuple[date, str]:
    if one.all_day:
        return date.fromisoformat(one.start[:10]), say("record.all_day")
    zone = ZoneInfo(one.tz) if one.tz else zones.home()
    start = datetime.fromisoformat(one.start).astimezone(zone)
    end = datetime.fromisoformat(one.end).astimezone(zone)
    return start.date(), f"{start:%H:%M}–{end:%H:%M}"


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    own = {
        one.id: one.name
        for one in await calendar.calendars(connection, create_default=False)
        if one.origin == "own" and one.app is None
    }
    if not own:
        return []
    first = await connection.scalar(FIRST, {"calendars": list(own)})
    if first is None:
        return []
    start = first.astimezone(UTC) - timedelta(days=1)
    until = datetime.now(UTC) + AHEAD
    found: list[calendar.Occurrence] = []
    while start < until:
        end = min(start + timedelta(days=calendar.MAX_WINDOW_DAYS), until)
        found.extend(await calendar.occurrences(connection, start, end, list(own)))
        start = end
    lines: dict[date, list[tuple[str, str]]] = defaultdict(list)
    seen: set[str] = set()
    for one in found:
        if one.id in seen or one.status != "confirmed":
            continue
        seen.add(one.id)
        day, when = _when(one)
        line = f"- {when} · {one.title}"
        if one.location:
            line += f" · {one.location}"
        if len(own) > 1 and one.calendar_id in own:
            line += f" · {own[one.calendar_id]}"
        lines[day].append(("" if one.all_day else when, line))
    return [
        contracts.record(
            id=f"day:{day.isoformat()}",
            title=say("record.agenda"),
            kind=say("record.day"),
            href="/planner/",
            day=day,
            properties={"events": len(told)},
            body="\n".join(line for _, line in sorted(told)),
        )
        for day, told in sorted(lines.items())
    ]
