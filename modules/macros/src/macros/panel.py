from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from macros import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Macros aún no tiene nada que contar")


async def build(connection: AsyncConnection) -> dict:
    found = await gather(
        connection, widgets.RENDERERS, ["today", "macros_today", "goals_today", "week_short", "log"]
    )
    today = ready(found.get("today"))
    blocks = blocks_of("ring", found.get("today") or {}, label="Hoy", hue=4)
    blocks += blocks_of("stats", found.get("macros_today") or {})
    blocks += blocks_of("list", found.get("goals_today") or {}, label="Objetivos de hoy")
    blocks += [
        dict(b, detail=True)
        for b in blocks_of("list", found.get("week_short") or {}, label="Lo que falta esta semana")
    ]
    if not blocks:
        raise nothing()
    headlines = []
    if today.get("value") is not None and today.get("target"):
        left = round(today["target"] - today["value"])
        unit = today.get("unit") or "kcal"
        if left >= 0:
            headlines.append(
                {
                    "text": f"Te quedan {left:,} {unit} hoy".replace(",", "."),
                    "emphasis": f"{left:,} {unit}".replace(",", "."),
                    "status": f"{left:,} {unit}".replace(",", "."),
                    "priority": 35,
                }
            )
        else:
            headlines.append(
                {
                    "text": f"Hoy te has pasado {-left:,} {unit}".replace(",", "."),
                    "emphasis": f"{-left:,} {unit}".replace(",", "."),
                    "tone": "warning",
                    "status": "Pasado",
                    "priority": 45,
                }
            )
    actions = [
        {"label": a["label"][:60], "href": a["href"]}
        for a in ready(found.get("log")).get("actions", [])[:3]
        if str(a.get("href", "")).startswith("/macros")
    ]
    actions.append({"label": "Abrir Macros", "href": "/macros/"})
    tabs = [{"id": "comida", "label": "Comida", "blocks": blocks, "actions": actions[:4]}]
    questions = [
        {
            "text": "¿Cuánto me queda por comer?",
            "words": ["comida", "calorias", "kcal", "macros", "proteina", "comer"],
            "tab": "comida",
        }
    ]
    return panel("health", order=30, headlines=headlines, tabs=tabs, questions=questions)
