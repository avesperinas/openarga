from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from notebook import widgets
from notebook.words import say, words


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Notebook has nothing to tell yet")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["today", "recent", "review"])
    tabs = [
        {
            "id": tab,
            "label": label,
            "blocks": blocks_of("list", found.get(key) or {}, label=label),
            "actions": [{"label": say("panel.open"), "href": "/notebook/"}],
        }
        for tab, key, label in (
            ("today", "today", say("panel.today")),
            ("recent", "recent", say("panel.recent")),
            ("review", "review", say("panel.review")),
        )
    ]
    tabs = [tab for tab in tabs if tab["blocks"]]
    if not tabs:
        raise nothing()
    ids = {tab["id"] for tab in tabs}
    questions = [
        q
        for q in (
            {
                "text": say("panel.ask_today"),
                "words": words("panel.ask_today_words"),
                "tab": "today",
            },
            {
                "text": say("panel.ask_review"),
                "words": words("panel.ask_review_words"),
                "tab": "review",
            },
        )
        if q["tab"] in ids
    ]
    return panel("mind", order=10, tabs=tabs, questions=questions)
