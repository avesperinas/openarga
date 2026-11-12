from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from insights import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Insights aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["latest"])
    rows = ready(found.get("latest")).get("rows", [])
    blocks = blocks_of("list", found.get("latest") or {}, label="Lo último")
    if not blocks:
        raise nothing()
    headlines = []
    if rows:
        headlines.append(
            {"text": f"Insights: {rows[0]['label']}"[:200], "status": "Novedad", "priority": 30}
        )
    tabs = [
        {
            "id": "insights",
            "label": "Insights",
            "blocks": blocks,
            "actions": [{"label": "Abrir Insights", "href": "/insights/"}],
        }
    ]
    questions = [
        {
            "text": "¿Qué ha notado Insights?",
            "words": ["insights", "patrones", "consejos", "insights"],
            "tab": "insights",
        }
    ]
    return panel("mind", order=20, headlines=headlines, tabs=tabs, questions=questions)
