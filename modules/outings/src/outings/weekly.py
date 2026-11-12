from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncConnection

from outings import by_hand, hub

MADRID = ZoneInfo("Europe/Madrid")
CAPABILITY = "claude.run"
FROM_HOUR = 6
EVERY_SECONDS = 3600.0
ASKED: dict[object, float] = {}


def key(now: datetime) -> str | None:
    local = now.astimezone(MADRID)
    if local.weekday() == 0 and local.hour < FROM_HOUR:
        return None
    year, week, _ = local.isocalendar()
    return f"agenda:{year}-W{week:02d}"


def due(user: object, clock: float | None = None) -> bool:
    clock = time.monotonic() if clock is None else clock
    if clock - ASKED.get(user, -EVERY_SECONDS) < EVERY_SECONDS:
        return False
    ASKED[user] = clock
    return True


async def ask(connection: AsyncConnection, now: datetime) -> dict[str, Any] | None:
    week = key(now)
    if week is None:
        return None
    body = {
        "key": week,
        "prompt": await by_hand.brief(connection),
        "tools": ["WebSearch", "WebFetch"],
        "wait_for_room": True,
    }
    try:
        response = await hub.ask(CAPABILITY, body, seconds=30)
    except httpx.HTTPError:
        return None
    return response.json() if response.status_code == 200 else None
