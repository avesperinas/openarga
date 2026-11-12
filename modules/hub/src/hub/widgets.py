from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from hub import connections


async def status(connection: AsyncConnection, now: datetime | None = None) -> dict:
    kind = "list"
    now = now or datetime.now(UTC)
    found = await connections.listed(connection, now)
    if not found:
        return envelope(kind, "empty", {"detail": "nada conectado todavía"})
    ordered = sorted(found, key=lambda item: connections.URGENCY[item.state])
    attention = [item for item in ordered if connections.needs_attention(item)]
    return envelope(
        kind,
        "ready",
        {
            "rows": [
                {
                    "label": item.label,
                    "value": connections.BRIEF[item.state],
                    "tone": connections.TONE[item.state],
                }
                for item in ordered
            ],
            "detail": attention[0].reason if attention else "todo al día",
        },
    )


RENDERERS = {"status": status}
