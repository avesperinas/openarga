from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from goals import widgets
from goals.common import plural, t


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail=t("panel.empty"))


async def build(connection: AsyncConnection) -> dict:
    found = await gather(
        connection,
        widgets.RENDERERS,
        ["today", "overdue"],
    )
    today = ready(found.get("today")).get("tasks", [])
    late = ready(found.get("overdue")).get("tasks", [])
    pending = [one for one in today if not one.get("done")]
    headlines = []
    if late:
        headlines.append(
            {
                "text": plural("panel.overdue", len(late)),
                "emphasis": f"{len(late)}",
                "tone": "warning",
                "status": plural("panel.overdue_status", len(late)),
                "priority": 60,
            }
        )
    elif pending:
        headlines.append(
            {
                "text": plural("panel.today", len(pending)),
                "emphasis": str(len(pending)),
                "status": plural("panel.today_status", len(pending)),
                "priority": 45,
            }
        )
    else:
        headlines.append(
            {
                "text": t("panel.clear"),
                "tone": "positive",
                "status": t("panel.clear_status"),
                "priority": 20,
            }
        )
    label = t("panel.for_today")
    blocks = blocks_of("tasks", found.get("today") or {}, label=label, widget="today") or [
        {"type": "tasks", "label": label, "widget": "today", "items": []}
    ]
    blocks[0]["add"] = t("panel.add")
    tabs = [
        {
            "id": "tasks",
            "label": t("panel.tasks"),
            "blocks": blocks,
            "actions": [{"label": t("panel.open"), "href": "/goals"}],
        }
    ]
    questions = [
        {
            "text": t("panel.question"),
            "words": t("panel.words").split(","),
            "tab": "tasks",
        }
    ]
    return panel("day", order=20, headlines=headlines, tabs=tabs, questions=questions)
