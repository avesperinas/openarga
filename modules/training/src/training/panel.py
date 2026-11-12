from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from training import widgets
from training.text import t


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail=t("panel.empty"))


PARTS = {
    "push": ["chest", "shoulders", "arms"],
    "pull": ["back", "arms"],
    "leg": ["legs"],
    "full": ["chest", "back", "legs", "core"],
}


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["next", "week"])
    nxt = ready(found.get("next"))
    week = ready(found.get("week"))
    blocks = []
    headlines = []
    if nxt.get("value") is not None:
        feature = {
            "type": "feature",
            "eyebrow": t("panel.next"),
            "title": str(nxt["value"])[:200],
            "action": t("panel.start"),
            "href": "/training/",
        }
        if nxt.get("detail"):
            feature["text"] = str(nxt["detail"])[:200]
        if nxt.get("icon") in PARTS:
            feature["body"] = PARTS[nxt["icon"]]
        blocks.append(feature)
        headlines.append(
            {
                "text": t("panel.due", name=nxt["value"]),
                "emphasis": str(nxt["value"]),
                "status": str(nxt["value"])[:60],
                "priority": 40,
            }
        )
    blocks += blocks_of("ring", found.get("week") or {}, label=t("panel.this_week"), hue=4)
    if not blocks:
        raise nothing()
    if week.get("value") is not None and week.get("target") and week["value"] >= week["target"]:
        headlines.append(
            {
                "text": t("panel.week_done"),
                "tone": "positive",
                "status": t("panel.done"),
                "priority": 45,
            }
        )
    tabs = [
        {
            "id": "training",
            "label": t("panel.tab"),
            "blocks": blocks,
            "actions": [{"label": t("panel.open"), "href": "/training/"}],
        }
    ]
    questions = [
        {
            "text": t("panel.question"),
            "words": t("panel.words").split(","),
            "tab": "training",
        }
    ]
    return panel("health", order=20, headlines=headlines, tabs=tabs, questions=questions)
