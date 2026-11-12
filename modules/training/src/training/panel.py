from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from training import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Training aún no tiene nada que contar")


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
            "eyebrow": "Siguiente sesión",
            "title": str(nxt["value"])[:200],
            "action": "Empezar",
            "href": "/training/",
        }
        if nxt.get("detail"):
            feature["text"] = str(nxt["detail"])[:200]
        if nxt.get("icon") in PARTS:
            feature["body"] = PARTS[nxt["icon"]]
        blocks.append(feature)
        headlines.append(
            {
                "text": f"Toca {nxt['value']}",
                "emphasis": str(nxt["value"]),
                "status": str(nxt["value"])[:60],
                "priority": 40,
            }
        )
    blocks += blocks_of("ring", found.get("week") or {}, label="Esta semana", hue=4)
    if not blocks:
        raise nothing()
    if week.get("value") is not None and week.get("target") and week["value"] >= week["target"]:
        headlines.append(
            {
                "text": "Semana de entreno cumplida",
                "tone": "positive",
                "status": "Cumplida",
                "priority": 45,
            }
        )
    tabs = [
        {
            "id": "entreno",
            "label": "Entreno",
            "blocks": blocks,
            "actions": [{"label": "Abrir Training", "href": "/training/"}],
        }
    ]
    questions = [
        {
            "text": "¿Qué toca entrenar?",
            "words": ["entreno", "entrenar", "gimnasio", "sesion", "rutina"],
            "tab": "entreno",
        }
    ]
    return panel("health", order=20, headlines=headlines, tabs=tabs, questions=questions)
