from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from shopping import widgets
from shopping.catalog import t


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail=t("panel.nothing"))


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["list", "due"])
    body = ready(found.get("list"))
    pending = [one for one in body.get("tasks", []) if not one.get("done")]
    blocks = blocks_of(
        "tasks",
        found.get("list") or {"state": "ready", "body": {"tasks": []}},
        label=t("panel.list"),
        widget="list",
    )
    if not blocks:
        blocks = [{"type": "tasks", "label": t("panel.list"), "widget": "list", "items": []}]
    blocks[0]["add"] = t("panel.add")
    blocks += blocks_of("list", found.get("due") or {}, label=t("panel.due"))
    headlines = []
    if pending:
        headlines.append(
            {
                "text": (
                    t("panel.missing_one")
                    if len(pending) == 1
                    else t("panel.missing_other", count=len(pending))
                ),
                "emphasis": str(len(pending)),
                "status": (
                    t("panel.status_one")
                    if len(pending) == 1
                    else t("panel.status_other", count=len(pending))
                ),
                "priority": 40,
            }
        )
    tabs = [
        {
            "id": "list",
            "label": t("panel.list"),
            "blocks": blocks,
            "actions": [{"label": t("panel.open"), "href": "/shopping/"}],
        }
    ]
    questions = [
        {
            "text": t("panel.question"),
            "words": t("panel.words").split(","),
            "tab": "list",
        }
    ]
    return panel("home", order=10, headlines=headlines, tabs=tabs, questions=questions)
