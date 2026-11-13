from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from library import widgets
from library.words import say, words


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Library has nothing to tell yet")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["reading", "goal", "pages"])
    goal = ready(found.get("goal"))
    blocks = blocks_of("ring", found.get("goal") or {}, label=say("panel.goal"), hue=5)
    blocks += blocks_of("bars", found.get("pages") or {}, label=say("panel.pages"))
    blocks += blocks_of("list", found.get("reading") or {}, label=say("panel.reading"))
    if not blocks:
        raise nothing()
    headlines = []
    if goal.get("value") is not None and goal.get("expected") is not None:
        ahead = round(goal["value"] - goal["expected"])
        if ahead >= 0:
            headlines.append(
                {
                    "text": say(
                        "panel.on_pace", value=round(goal["value"]), target=round(goal["target"])
                    ),
                    "emphasis": say("panel.on_pace.emphasis"),
                    "tone": "positive",
                    "status": say("panel.on_pace.status"),
                    "priority": 25,
                }
            )
        else:
            headlines.append(
                {
                    "text": say(
                        "panel.behind.one" if ahead == -1 else "panel.behind.other", count=-ahead
                    ),
                    "emphasis": f"{-ahead}",
                    "tone": "warning",
                    "status": say("panel.behind.status"),
                    "priority": 30,
                }
            )
    tabs = [
        {
            "id": "reading",
            "label": say("panel.tab"),
            "blocks": blocks,
            "actions": [{"label": say("panel.open"), "href": "/library/"}],
        }
    ]
    questions = [
        {
            "text": say("panel.ask"),
            "words": words("panel.ask.words"),
            "tab": "reading",
        }
    ]
    return panel("leisure", order=30, headlines=headlines, tabs=tabs, questions=questions)
