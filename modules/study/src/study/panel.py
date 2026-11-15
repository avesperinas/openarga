from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel, tile_of
from study import widgets
from study.words import say, words


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail=say("panel.nothing"))


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["upnext", "progress", "average"])
    nxt = ready(found.get("upnext")).get("events", [])
    blocks = blocks_of("progress", found.get("progress") or {}, label=say("panel.progress"), hue=6)
    tiles = [t for t in (tile_of("kpi", found.get("average"), say("panel.average")),) if t]
    if tiles:
        blocks.append({"type": "tiles", "items": tiles})
    blocks += blocks_of("upnext", found.get("upnext") or {}, label=say("panel.up_next"))
    if not blocks:
        raise nothing()
    headlines = []
    if nxt:
        headlines.append(
            {
                "text": say("panel.headline", title=nxt[0]["title"])[:200],
                "emphasis": str(nxt[0]["title"])[:150],
                "status": say("panel.status"),
                "priority": 35,
            }
        )
    tabs = [
        {
            "id": "master",
            "label": say("panel.tab"),
            "blocks": blocks,
            "actions": [{"label": say("panel.open"), "href": "/study/"}],
        }
    ]
    questions = [
        {
            "text": say("panel.question"),
            "words": words("panel.words"),
            "tab": "master",
        }
    ]
    return panel("work", order=20, headlines=headlines, tabs=tabs, questions=questions)
