from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel, tile_of
from vitals import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Vitals aún no tiene nada que contar")


RINGS = [("readiness", "Disposición", 5), ("sleep_score", "Sueño", 1), ("steps_today", "Pasos", 2)]


async def build(connection: AsyncConnection) -> dict:
    ids = [
        "readiness", "sleep_score", "steps_today", "sleep", "weight", "resting_heart", "hrv",
        "sleep_week", "ldl", "vo2max", "steps_week", "training_load", "training_week",
        "last_workout",
    ]  # fmt: skip
    found = await gather(connection, widgets.RENDERERS, ids)
    rings = []
    for key, label, hue in RINGS:
        body = ready(found.get(key))
        if body.get("value") is not None and body.get("target"):
            value = body["value"]
            shown = (
                f"{value / 1000:.1f}k".replace(".", ",")
                if key == "steps_today" and value >= 1000
                else str(round(value))
            )
            rings.append(
                {
                    "label": label,
                    "value": shown,
                    "share": max(0.0, value / body["target"]),
                    "hue": hue,
                }
            )
    headlines = []
    readiness = ready(found.get("readiness")).get("value")
    if readiness is not None:
        if readiness >= 70:
            headlines.append(
                {
                    "text": f"Llegas bien al día: {round(readiness)} de disposición",
                    "emphasis": f"{round(readiness)} de disposición",
                    "tone": "positive",
                    "status": "Listo",
                    "priority": 50,
                }
            )
        elif readiness < 45:
            headlines.append(
                {
                    "text": f"Hoy mejor suave: {round(readiness)} de disposición",
                    "emphasis": "mejor suave",
                    "tone": "warning",
                    "status": "Descansa",
                    "priority": 55,
                }
            )
        else:
            headlines.append(
                {
                    "text": f"Un día normal: {round(readiness)} de disposición",
                    "emphasis": f"{round(readiness)}",
                    "status": "Normal",
                    "priority": 35,
                }
            )
    hoy = []
    if rings:
        hoy.append({"type": "rings", "items": rings})
    tiles = [
        t
        for t in (
            tile_of("kpi-delta", found.get("sleep"), "Sueño"),
            tile_of("kpi-delta", found.get("weight"), "Peso"),
            tile_of("kpi-delta", found.get("resting_heart"), "FC en reposo"),
            tile_of("kpi-delta", found.get("hrv"), "VFC"),
        )
        if t
    ]
    if tiles:
        hoy.append({"type": "tiles", "items": tiles})
    sueno = blocks_of("kpi-delta", found.get("sleep") or {}, label="Sueño") + blocks_of(
        "bars", found.get("sleep_week") or {}, label="La semana"
    )
    cuerpo = blocks_of("kpi-delta", found.get("weight") or {}, label="Peso")
    more = [
        t
        for t in (
            tile_of("kpi-delta", found.get("ldl"), "Colesterol LDL"),
            tile_of("kpi-delta", found.get("vo2max"), "VO₂ máx."),
            tile_of("kpi-delta", found.get("resting_heart"), "FC en reposo"),
        )
        if t
    ]
    if more:
        cuerpo.append({"type": "tiles", "items": more})
    actividad = blocks_of(
        "bars", found.get("steps_week") or {}, label="Pasos de la semana"
    ) + blocks_of("progress", found.get("training_load") or {}, label="Carga de la semana", hue=4)
    actividad += blocks_of("stats", found.get("training_week") or {}) + [
        dict(b, detail=True) for b in blocks_of("stats", found.get("last_workout") or {})
    ]
    tabs = [
        {
            "id": tab,
            "label": label,
            "blocks": blocks,
            "actions": [{"label": "Abrir Vitals", "href": "/vitals/"}],
        }
        for tab, label, blocks in (
            ("hoy", "Hoy", hoy),
            ("sueno", "Sueño", sueno),
            ("cuerpo", "Cuerpo", cuerpo),
            ("actividad", "Actividad", actividad),
        )
        if blocks
    ]
    if not tabs:
        raise nothing()
    ids_ = {tab["id"] for tab in tabs}
    questions = [
        q
        for q in (
            {
                "text": "¿Cómo llego hoy?",
                "words": ["disposicion", "como estoy", "energia", "recuperacion"],
                "tab": "hoy",
            },
            {
                "text": "¿He dormido bien?",
                "words": ["sueno", "dormir", "dormido", "descanso"],
                "tab": "sueno",
            },
            {
                "text": "¿Cómo va mi peso?",
                "words": ["peso", "kilos", "cuerpo", "colesterol"],
                "tab": "cuerpo",
            },
            {
                "text": "¿Cuánto me he movido?",
                "words": ["pasos", "actividad", "andar", "carga"],
                "tab": "actividad",
            },
        )
        if q["tab"] in ids_
    ]
    return panel("health", order=10, headlines=headlines, tabs=tabs, questions=questions)
