from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from goals import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="KPIs aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(
        connection,
        widgets.RENDERERS,
        ["today", "overdue"],
    )
    today = ready(found.get("today")).get("tasks", [])
    late = ready(found.get("overdue")).get("tasks", [])
    pending = [one for one in today if not one.get("done")]
    headlines = []
    if late:
        headlines.append(
            {
                "text": f"Tienes {len(late)} "
                + ("tarea vencida" if len(late) == 1 else "tareas vencidas"),
                "emphasis": f"{len(late)}",
                "tone": "warning",
                "status": "1 vencida" if len(late) == 1 else f"{len(late)} vencidas",
                "priority": 60,
            }
        )
    elif pending:
        headlines.append(
            {
                "text": f"{len(pending)} {'tarea' if len(pending) == 1 else 'tareas'} para hoy",
                "emphasis": str(len(pending)),
                "status": "1 tarea" if len(pending) == 1 else f"{len(pending)} tareas",
                "priority": 45,
            }
        )
    else:
        headlines.append(
            {
                "text": "Nada pendiente para hoy",
                "tone": "positive",
                "status": "Al día",
                "priority": 20,
            }
        )
    blocks = blocks_of("tasks", found.get("today") or {}, label="Para hoy", widget="today") or [
        {"type": "tasks", "label": "Para hoy", "widget": "today", "items": []}
    ]
    blocks[0]["add"] = "Añadir una tarea para hoy"
    tabs = [
        {
            "id": "tareas",
            "label": "Tareas",
            "blocks": blocks,
            "actions": [{"label": "Abrir tareas", "href": "/goals"}],
        }
    ]
    questions = [
        {
            "text": "¿Qué tengo que hacer?",
            "words": ["tareas", "pendiente", "hacer", "goals", "vencidas"],
            "tab": "tareas",
        }
    ]
    return panel("day", order=20, headlines=headlines, tabs=tabs, questions=questions)
