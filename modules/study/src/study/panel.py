from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel, tile_of
from study import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Study aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["upnext", "progress", "average"])
    nxt = ready(found.get("upnext")).get("events", [])
    blocks = blocks_of("progress", found.get("progress") or {}, label="Progreso", hue=6)
    tiles = [t for t in (tile_of("kpi", found.get("average"), "Media"),) if t]
    if tiles:
        blocks.append({"type": "tiles", "items": tiles})
    blocks += blocks_of("upnext", found.get("upnext") or {}, label="Lo próximo")
    if not blocks:
        raise nothing()
    headlines = []
    if nxt:
        headlines.append(
            {
                "text": f"Lo próximo en el máster: {nxt[0]['title']}"[:200],
                "emphasis": str(nxt[0]["title"])[:150],
                "status": "Máster",
                "priority": 35,
            }
        )
    tabs = [
        {
            "id": "master",
            "label": "Máster",
            "blocks": blocks,
            "actions": [{"label": "Abrir Study", "href": "/study/"}],
        }
    ]
    questions = [
        {
            "text": "¿Qué tengo en el máster?",
            "words": ["master", "clase", "entrega", "examen", "study", "notas"],
            "tab": "master",
        }
    ]
    return panel("work", order=20, headlines=headlines, tabs=tabs, questions=questions)
