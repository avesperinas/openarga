from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel, tile_of
from travel import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Travel aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(
        connection, widgets.RENDERERS, ["next_trip", "countries", "last_trip", "by_year"]
    )
    nxt = ready(found.get("next_trip")).get("events", [])
    days = None
    if nxt:
        try:
            days = (datetime.fromisoformat(nxt[0]["at"]).date() - datetime.now().date()).days
        except ValueError:
            days = None
    blocks: list[dict] = []
    if nxt:
        when = (
            None
            if days is None or days < 0
            else "hoy"
            if days == 0
            else "mañana"
            if days == 1
            else f"en {days} días"
        )
        blocks.append(
            {
                "type": "feature",
                "eyebrow": "Próximo viaje",
                "title": str(nxt[0]["title"])[:200],
                **({"text": when} if when else {}),
                "action": "Ver el viaje",
                "href": "/travel/",
            }
        )
    tiles = [t for t in (tile_of("kpi", found.get("countries"), "Países"),) if t]
    if tiles:
        blocks.append({"type": "tiles", "items": tiles})
    blocks += blocks_of("bars", found.get("by_year") or {}, label="Viajes por año")
    blocks += [
        dict(b, detail=True)
        for b in blocks_of("upnext", found.get("next_trip") or {}, label="Lo que viene")
        + blocks_of("upnext", found.get("last_trip") or {}, label="Último viaje")
    ]
    if not blocks:
        raise nothing()
    headlines = []
    if nxt:
        title = str(nxt[0]["title"])
        if days is not None and days >= 0:
            when = "hoy" if days == 0 else "mañana" if days == 1 else f"en {days} días"
            headlines.append(
                {
                    "text": f"{title}, {when}",
                    "emphasis": title,
                    "status": when,
                    "priority": 40 if days > 7 else 50,
                }
            )
    tabs = [
        {
            "id": "viajes",
            "label": "Viajes",
            "blocks": blocks,
            "actions": [{"label": "Abrir Travel", "href": "/travel/"}],
        }
    ]
    questions = [
        {
            "text": "¿Cuándo es el próximo viaje?",
            "words": ["viaje", "viajes", "vacaciones", "paises", "lisboa"],
            "tab": "viajes",
        }
    ]
    return panel("leisure", order=10, headlines=headlines, tabs=tabs, questions=questions)
