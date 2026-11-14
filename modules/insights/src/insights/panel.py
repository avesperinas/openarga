from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from insights import widgets
from insights.words import say, words


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Insights has nothing to tell yet")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["latest"])
    rows = ready(found.get("latest")).get("rows", [])
    blocks = blocks_of("list", found.get("latest") or {}, label=say("panel.latest"))
    if not blocks:
        raise nothing()
    headlines = []
    if rows:
        headlines.append(
            {
                "text": f"Insights: {rows[0]['label']}"[:200],
                "status": say("panel.new"),
                "priority": 30,
            }
        )
    tabs = [
        {
            "id": "insights",
            "label": "Insights",
            "blocks": blocks,
            "actions": [{"label": say("panel.open"), "href": "/insights/"}],
        }
    ]
    questions = [
        {
            "text": say("panel.ask"),
            "words": words("panel.ask_words"),
            "tab": "insights",
        }
    ]
    return panel("mind", order=20, headlines=headlines, tabs=tabs, questions=questions)
