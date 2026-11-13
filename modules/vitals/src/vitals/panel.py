from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel, tile_of
from vitals import widgets
from vitals.text import number, t


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail=t("panel.empty"))


RINGS = [
    ("readiness", "panel.readiness", 5),
    ("sleep_score", "panel.sleep", 1),
    ("steps_today", "panel.steps", 2),
]


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
                f"{number(value / 1000, 1)}k"
                if key == "steps_today" and value >= 1000
                else str(round(value))
            )
            rings.append(
                {
                    "label": t(label),
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
                    "text": t("panel.ready_text", value=round(readiness)),
                    "emphasis": t("panel.ready_emphasis", value=round(readiness)),
                    "tone": "positive",
                    "status": t("panel.ready_status"),
                    "priority": 50,
                }
            )
        elif readiness < 45:
            headlines.append(
                {
                    "text": t("panel.easy_text", value=round(readiness)),
                    "emphasis": t("panel.easy_emphasis"),
                    "tone": "warning",
                    "status": t("panel.easy_status"),
                    "priority": 55,
                }
            )
        else:
            headlines.append(
                {
                    "text": t("panel.normal_text", value=round(readiness)),
                    "emphasis": f"{round(readiness)}",
                    "status": t("panel.normal_status"),
                    "priority": 35,
                }
            )
    today = []
    if rings:
        today.append({"type": "rings", "items": rings})
    tiles = [
        tile
        for tile in (
            tile_of("kpi-delta", found.get("sleep"), t("panel.sleep")),
            tile_of("kpi-delta", found.get("weight"), t("panel.weight")),
            tile_of("kpi-delta", found.get("resting_heart"), t("panel.resting_hr")),
            tile_of("kpi-delta", found.get("hrv"), t("panel.hrv")),
        )
        if tile
    ]
    if tiles:
        today.append({"type": "tiles", "items": tiles})
    asleep = blocks_of("kpi-delta", found.get("sleep") or {}, label=t("panel.sleep")) + blocks_of(
        "bars", found.get("sleep_week") or {}, label=t("panel.the_week")
    )
    figure = blocks_of("kpi-delta", found.get("weight") or {}, label=t("panel.weight"))
    more = [
        tile
        for tile in (
            tile_of("kpi-delta", found.get("ldl"), t("panel.ldl")),
            tile_of("kpi-delta", found.get("vo2max"), t("panel.vo2max")),
            tile_of("kpi-delta", found.get("resting_heart"), t("panel.resting_hr")),
        )
        if tile
    ]
    if more:
        figure.append({"type": "tiles", "items": more})
    activity = blocks_of(
        "bars", found.get("steps_week") or {}, label=t("panel.steps_week")
    ) + blocks_of("progress", found.get("training_load") or {}, label=t("panel.load_week"), hue=4)
    activity += blocks_of("stats", found.get("training_week") or {}) + [
        dict(b, detail=True) for b in blocks_of("stats", found.get("last_workout") or {})
    ]
    tabs = [
        {
            "id": tab,
            "label": label,
            "blocks": blocks,
            "actions": [{"label": t("panel.open"), "href": "/vitals/"}],
        }
        for tab, label, blocks in (
            ("today", t("panel.today"), today),
            ("sleep", t("panel.sleep"), asleep),
            ("body", t("panel.body"), figure),
            ("activity", t("panel.activity"), activity),
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
                "text": t("panel.q_today"),
                "words": t("panel.w_today").split(","),
                "tab": "today",
            },
            {
                "text": t("panel.q_sleep"),
                "words": t("panel.w_sleep").split(","),
                "tab": "sleep",
            },
            {
                "text": t("panel.q_weight"),
                "words": t("panel.w_weight").split(","),
                "tab": "body",
            },
            {
                "text": t("panel.q_activity"),
                "words": t("panel.w_activity").split(","),
                "tab": "activity",
            },
        )
        if q["tab"] in ids_
    ]
    return panel("health", order=10, headlines=headlines, tabs=tabs, questions=questions)
