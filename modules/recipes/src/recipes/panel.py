from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from recipes import widgets
from recipes.catalog import t


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Recipes has nothing to tell yet")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["quick", "recipes"])
    blocks = blocks_of("list", found.get("quick") or {}, label=t("panel.quick")) + blocks_of(
        "stats", found.get("recipes") or {}
    )
    if not blocks:
        raise nothing()
    tabs = [
        {
            "id": "kitchen",
            "label": t("panel.kitchen"),
            "blocks": blocks,
            "actions": [{"label": t("panel.book"), "href": "/recipes/"}],
        }
    ]
    questions = [
        {
            "text": t("panel.question"),
            "words": t("panel.words").split(","),
            "tab": "kitchen",
        }
    ]
    return panel("home", order=30, tabs=tabs, questions=questions)
