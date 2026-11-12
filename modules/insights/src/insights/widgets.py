from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from insights import insights, pills

MADRID = ZoneInfo("Europe/Madrid")

KINDS = {"latest": "list", "today": "list"}

ROWS = 8


async def latest(connection: AsyncConnection) -> dict:
    found = await insights.recent(connection, limit=ROWS)
    if not found:
        return envelope(KINDS["latest"], "empty", {"detail": "todavía no te ha dicho nada"})
    unread = sum(1 for one in found if one.read_at is None)
    body: dict = {
        "rows": [{"label": one.title, "value": f"{one.created_at:%d/%m}"} for one in found]
    }
    if unread:
        body["detail"] = f"{unread} sin leer" if unread > 1 else "1 sin leer"
    return envelope(KINDS["latest"], "ready", body)


async def today(connection: AsyncConnection) -> dict:
    day = datetime.now(MADRID).date()
    pill = await pills.daily(connection, day)
    found = await pills.facts(connection, day)
    rows = []
    if pill is not None:
        rows.append({"label": pill.headline, "value": f"{pill.minutes} min"})
    rows += [{"label": one.text, "value": ""} for one in found[: ROWS - len(rows)]]
    if not rows:
        return envelope(KINDS["today"], "empty", {"detail": "tu píldora llega a tu hora"})
    body: dict = {"rows": rows}
    if pill is not None and pill.read_at is None:
        body["detail"] = "sin leer"
    return envelope(KINDS["today"], "ready", body)


RENDERERS = {"latest": latest, "today": today}
