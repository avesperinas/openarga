from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from notebook import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Notebook aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["today", "recent", "review"])
    tabs = [
        {
            "id": tab,
            "label": label,
            "blocks": blocks_of("list", found.get(key) or {}, label=label),
            "actions": [{"label": "Abrir Notebook", "href": "/notebook/"}],
        }
        for tab, key, label in (
            ("hoy", "today", "Nota de hoy"),
            ("recientes", "recent", "Recientes"),
            ("repasar", "review", "Para repasar"),
        )
    ]
    tabs = [tab for tab in tabs if tab["blocks"]]
    if not tabs:
        raise nothing()
    ids = {tab["id"] for tab in tabs}
    questions = [
        q
        for q in (
            {
                "text": "¿Qué escribí hoy?",
                "words": ["nota", "notas", "diario", "hoy"],
                "tab": "hoy",
            },
            {
                "text": "¿Qué tengo que repasar?",
                "words": ["repasar", "repaso", "estudiar"],
                "tab": "repasar",
            },
        )
        if q["tab"] in ids
    ]
    return panel("mind", order=10, tabs=tabs, questions=questions)
