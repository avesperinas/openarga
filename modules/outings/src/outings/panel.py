from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from outings import widgets
from outings.words import say, words


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Outings has nothing to tell yet")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["weekend", "wishes"])
    plans = ready(found.get("weekend")).get("events", [])
    blocks = blocks_of("upnext", found.get("weekend") or {}, label=say("panel.weekend"))
    wishes = blocks_of("list", found.get("wishes") or {}, label=say("panel.wishes"))
    if not blocks and not wishes:
        raise nothing()
    headlines = []
    if plans:
        headlines.append(
            {
                "text": say("panel.headline", title=plans[0]["title"]),
                "emphasis": str(plans[0]["title"]),
                "status": say("panel.plans"),
                "priority": 30,
            }
        )
    tabs = []
    if blocks:
        tabs.append(
            {
                "id": "weekend",
                "label": say("panel.plans"),
                "blocks": blocks,
                "actions": [{"label": say("panel.explore"), "href": "/outings/explore"}],
            }
        )
    if wishes:
        tabs.append(
            {
                "id": "wishes",
                "label": say("panel.wishes"),
                "blocks": wishes,
                "actions": [{"label": say("panel.open"), "href": "/outings/"}],
            }
        )
    ids = {tab["id"] for tab in tabs}
    questions = [
        q
        for q in (
            {
                "text": say("panel.ask.weekend"),
                "words": words("panel.ask.weekend.words"),
                "tab": "weekend",
            },
            {
                "text": say("panel.ask.wishes"),
                "words": words("panel.ask.wishes.words"),
                "tab": "wishes",
            },
        )
        if q["tab"] in ids
    ]
    return panel("leisure", order=20, headlines=headlines, tabs=tabs, questions=questions)
