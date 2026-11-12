from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from recipes import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Argiñano aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["quick", "recipes"])
    blocks = blocks_of("list", found.get("quick") or {}, label="En media hora") + blocks_of(
        "stats", found.get("recipes") or {}
    )
    if not blocks:
        raise nothing()
    tabs = [
        {
            "id": "cocina",
            "label": "Cocina",
            "blocks": blocks,
            "actions": [{"label": "Recetario", "href": "/recipes/"}],
        }
    ]
    questions = [
        {
            "text": "¿Qué cocino?",
            "words": ["receta", "cocinar", "cenar", "comer", "recetas"],
            "tab": "cocina",
        }
    ]
    return panel("home", order=30, tabs=tabs, questions=questions)
