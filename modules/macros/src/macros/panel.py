from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from macros import catalog, widgets
from macros.catalog import t


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Macros has nothing to tell yet")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(
        connection, widgets.RENDERERS, ["today", "macros_today", "goals_today", "week_short", "log"]
    )
    today = ready(found.get("today"))
    blocks = blocks_of("ring", found.get("today") or {}, label=t("panel.today"), hue=4)
    blocks += blocks_of("stats", found.get("macros_today") or {})
    blocks += blocks_of("list", found.get("goals_today") or {}, label=t("panel.goals_today"))
    blocks += [
        dict(b, detail=True)
        for b in blocks_of("list", found.get("week_short") or {}, label=t("panel.week_short"))
    ]
    if not blocks:
        raise nothing()
    headlines = []
    if today.get("value") is not None and today.get("target"):
        left = round(today["target"] - today["value"])
        unit = today.get("unit") or "kcal"
        amount = f"{catalog.number(abs(left))} {unit}"
        if left >= 0:
            headlines.append(
                {
                    "text": t("panel.left", amount=amount),
                    "emphasis": amount,
                    "status": amount,
                    "priority": 35,
                }
            )
        else:
            headlines.append(
                {
                    "text": t("panel.over", amount=amount),
                    "emphasis": amount,
                    "tone": "warning",
                    "status": t("panel.over_status"),
                    "priority": 45,
                }
            )
    actions = [
        {"label": a["label"][:60], "href": a["href"]}
        for a in ready(found.get("log")).get("actions", [])[:3]
        if str(a.get("href", "")).startswith("/macros")
    ]
    actions.append({"label": t("panel.open"), "href": "/macros/"})
    tabs = [{"id": "food", "label": t("panel.food"), "blocks": blocks, "actions": actions[:4]}]
    questions = [
        {
            "text": t("panel.question"),
            "words": t("panel.words").split(","),
            "tab": "food",
        }
    ]
    return panel("health", order=30, headlines=headlines, tabs=tabs, questions=questions)
