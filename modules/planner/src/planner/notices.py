from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from planner import calendar

KIND = "event"
BEFORE = timedelta(minutes=15)
ALL_DAY_AT = time(9, 0)
AHEAD = timedelta(days=2)


def _when(start: datetime) -> str:
    return start.astimezone(notify.MADRID).strftime("%H:%M")


async def build(connection: AsyncConnection, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    own = [
        one.id
        for one in await calendar.calendars(connection, create_default=False)
        if one.origin == "own" and one.visible and one.display == "events"
    ]
    if not own:
        return []
    out = []
    for one in await calendar.occurrences(connection, now, now + AHEAD, own):
        if one.status != "confirmed":
            continue
        if one.all_day:
            day = date.fromisoformat(one.start[:10])
            at = notify.at(day, ALL_DAY_AT)
            body = "Hoy, todo el día"
        else:
            start = datetime.fromisoformat(one.start)
            at = start - BEFORE
            day = start.astimezone(notify.MADRID).date()
            body = f"A las {_when(start)}"
        if one.location:
            body = f"{body} · {one.location}"
        out.append(
            notify.notification(
                KIND,
                f"event:{one.id}:{one.start}",
                one.title,
                f"/planner/dia/{day.isoformat()}",
                at,
                body=body,
            )
        )
    return out
