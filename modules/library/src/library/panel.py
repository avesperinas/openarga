from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from library import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Library aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["reading", "goal", "pages"])
    goal = ready(found.get("goal"))
    blocks = blocks_of("ring", found.get("goal") or {}, label="Libros del año", hue=5)
    blocks += blocks_of("bars", found.get("pages") or {}, label="Páginas por mes")
    blocks += blocks_of("list", found.get("reading") or {}, label="Leyendo")
    if not blocks:
        raise nothing()
    headlines = []
    if goal.get("value") is not None and goal.get("expected") is not None:
        ahead = round(goal["value"] - goal["expected"])
        if ahead >= 0:
            headlines.append(
                {
                    "text": (
                        f"Vas al día con los libros: {round(goal['value'])} "
                        f"de {round(goal['target'])}"
                    ),
                    "emphasis": "al día",
                    "tone": "positive",
                    "status": "Al día",
                    "priority": 25,
                }
            )
        else:
            headlines.append(
                {
                    "text": f"Vas {-ahead} "
                    + ("libro" if ahead == -1 else "libros")
                    + " por detrás de tu meta",
                    "emphasis": f"{-ahead}",
                    "tone": "warning",
                    "status": "Por detrás",
                    "priority": 30,
                }
            )
    tabs = [
        {
            "id": "lectura",
            "label": "Lectura",
            "blocks": blocks,
            "actions": [{"label": "Abrir Library", "href": "/library/"}],
        }
    ]
    questions = [
        {
            "text": "¿Llego a mi meta de libros?",
            "words": ["libros", "leer", "lectura", "leyendo"],
            "tab": "lectura",
        }
    ]
    return panel("leisure", order=30, headlines=headlines, tabs=tabs, questions=questions)
