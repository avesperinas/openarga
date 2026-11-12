from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from shopping import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Shopping aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["list", "due"])
    body = ready(found.get("list"))
    pending = [one for one in body.get("tasks", []) if not one.get("done")]
    blocks = blocks_of(
        "tasks",
        found.get("list") or {"state": "ready", "body": {"tasks": []}},
        label="La compra",
        widget="list",
    )
    if not blocks:
        blocks = [{"type": "tasks", "label": "La compra", "widget": "list", "items": []}]
    blocks[0]["add"] = "Apuntar algo…"
    blocks += blocks_of("list", found.get("due") or {}, label="Se está acabando")
    headlines = []
    if pending:
        headlines.append(
            {
                "text": (
                    "Falta 1 cosa por comprar"
                    if len(pending) == 1
                    else f"Faltan {len(pending)} cosas por comprar"
                ),
                "emphasis": str(len(pending)),
                "status": "1 cosa" if len(pending) == 1 else f"{len(pending)} cosas",
                "priority": 40,
            }
        )
    tabs = [
        {
            "id": "compra",
            "label": "La compra",
            "blocks": blocks,
            "actions": [{"label": "Abrir Shopping", "href": "/shopping/"}],
        }
    ]
    questions = [
        {
            "text": "¿Qué falta en casa?",
            "words": ["compra", "lista", "super", "comprar", "falta"],
            "tab": "compra",
        }
    ]
    return panel("home", order=10, headlines=headlines, tabs=tabs, questions=questions)
