from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from outings import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Outings aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["weekend", "wishes"])
    plans = ready(found.get("weekend")).get("events", [])
    blocks = blocks_of("upnext", found.get("weekend") or {}, label="Este finde")
    wishes = blocks_of("list", found.get("wishes") or {}, label="Ganas")
    if not blocks and not wishes:
        raise nothing()
    headlines = []
    if plans:
        headlines.append(
            {
                "text": f"Este finde, {plans[0]['title']}",
                "emphasis": str(plans[0]["title"]),
                "status": "Planes",
                "priority": 30,
            }
        )
    tabs = []
    if blocks:
        tabs.append(
            {
                "id": "finde",
                "label": "Planes",
                "blocks": blocks,
                "actions": [{"label": "Explorar", "href": "/outings/"}],
            }
        )
    if wishes:
        tabs.append(
            {
                "id": "ganas",
                "label": "Ganas",
                "blocks": wishes,
                "actions": [{"label": "Abrir Outings", "href": "/outings/"}],
            }
        )
    ids = {tab["id"] for tab in tabs}
    questions = [
        q
        for q in (
            {
                "text": "¿Qué hago este finde?",
                "words": ["finde", "planes", "concierto", "ocio", "salir"],
                "tab": "finde",
            },
            {
                "text": "¿Qué ganas tengo?",
                "words": ["ganas", "deseos", "quiero hacer"],
                "tab": "ganas",
            },
        )
        if q["tab"] in ids
    ]
    return panel("leisure", order=20, headlines=headlines, tabs=tabs, questions=questions)
