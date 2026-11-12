from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from training import plan, training
from training.text import t

KINDS = {"week": "ring", "next": "kpi"}

ICONS = {
    "push": "push",
    "pull": "pull",
    "leg": "leg",
    "full": "kettlebell",
    "other": "dumbbell",
}

HUES = {"push": 4, "pull": 2, "leg": 1, "full": 5, "other": 8}


async def week(connection: AsyncConnection) -> dict:
    current = await training.week(connection, training.local_day(datetime.now(UTC)))
    today = training.local_day(datetime.now(UTC))
    elapsed = (today - current.monday).days + 1
    body = {
        "value": current.done,
        "target": current.goal,
        "label": t("widget.week", goal=current.goal),
        "expected": round(current.goal * elapsed / 7, 2),
    }
    if await plan.active_plan(connection) is None:
        return envelope(KINDS["week"], "empty", body)
    return envelope(KINDS["week"], "ready", body)


async def next_session(connection: AsyncConnection) -> dict:
    upcoming = await training.next_session(connection)
    if upcoming is None:
        return envelope(KINDS["next"], "empty", {"value": "—"})
    body: dict[str, Any] = {"value": upcoming.name}
    icon = ICONS.get(upcoming.kind)
    if icon:
        body["icon"] = icon
        body["icon_hue"] = HUES[upcoming.kind]
    return envelope(KINDS["next"], "ready", body)


RENDERERS = {"week": week, "next": next_session}
