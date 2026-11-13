from __future__ import annotations

import time
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import ai
from arga_contracts.ai import RunRequest, RunResponse
from outings import by_hand, hub
from outings.common import zone

FROM_HOUR = 6
EVERY_SECONDS = 3600.0
ASKED: dict[object, float] = {}


def key(now: datetime) -> str | None:
    local = now.astimezone(zone())
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


async def ask(connection: AsyncConnection, now: datetime) -> RunResponse | None:
    week = key(now)
    if week is None:
        return None
    body = RunRequest(role="smart", task=await by_hand.brief(connection), key=week, web=True)
    try:
        response = await hub.ask(ai.RUN, body.model_dump(), seconds=30)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return RunResponse.model_validate(response.json())
