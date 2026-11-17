from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel, tile_of
from travel import widgets
from travel.words import say, words


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def _when(days: int) -> str:
    if days == 0:
        return say("when.today")
    return say("when.tomorrow") if days == 1 else say("when.in_days", days=days)


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail=say("panel.nothing"))


async def build(connection: AsyncConnection) -> dict:
    found = await gather(
        connection, widgets.RENDERERS, ["next_trip", "countries", "last_trip", "by_year"]
    )
    nxt = ready(found.get("next_trip")).get("events", [])
    days = None
    if nxt:
        try:
            days = (datetime.fromisoformat(nxt[0]["at"]).date() - datetime.now().date()).days
        except ValueError:
            days = None
    blocks: list[dict] = []
    if nxt:
        when = None if days is None or days < 0 else _when(days)
        blocks.append(
            {
                "type": "feature",
                "eyebrow": say("panel.next_trip"),
                "title": str(nxt[0]["title"])[:200],
                **({"text": when} if when else {}),
                "action": say("panel.see_trip"),
                "href": "/travel/",
            }
        )
    tiles = [t for t in (tile_of("kpi", found.get("countries"), say("panel.countries")),) if t]
    if tiles:
        blocks.append({"type": "tiles", "items": tiles})
    blocks += blocks_of("bars", found.get("by_year") or {}, label=say("panel.by_year"))
    blocks += [
        dict(b, detail=True)
        for b in blocks_of("upnext", found.get("next_trip") or {}, label=say("panel.coming"))
        + blocks_of("upnext", found.get("last_trip") or {}, label=say("panel.last_trip"))
    ]
    if not blocks:
        raise nothing()
    headlines = []
    if nxt:
        title = str(nxt[0]["title"])
        if days is not None and days >= 0:
            when = _when(days)
            headlines.append(
                {
                    "text": f"{title}, {when}",
                    "emphasis": title,
                    "status": when,
                    "priority": 40 if days > 7 else 50,
                }
            )
    tabs = [
        {
            "id": "trips",
            "label": say("panel.tab"),
            "blocks": blocks,
            "actions": [{"label": say("panel.open"), "href": "/travel/"}],
        }
    ]
    questions = [
        {
            "text": say("panel.question"),
            "words": words("panel.words"),
            "tab": "trips",
        }
    ]
    return panel("leisure", order=10, headlines=headlines, tabs=tabs, questions=questions)
