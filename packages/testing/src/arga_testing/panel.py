from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from arga_widgets import validate
from arga_widgets.panel import served

DAY = "2026-11-06"


def _at(day: int, hour: int, minute: int = 0) -> str:
    return f"2026-11-{6 + day:02d}T{hour:02d}:{minute:02d}:00+01:00"


SAMPLES: dict[str, dict[str, Any]] = {
    "kpi": {"value": 412, "unit": "", "detail": "de muestra"},
    "kpi-delta": {
        "value": 74.2,
        "previous": 75.8,
        "unit": "kg",
        "since": "en 12 semanas",
        "good_when": "down",
        "series": [75.8, 75.4, 75.0, 74.8, 74.5, 74.2],
    },
    "chart": {"series": [12, 18, 9, 22, 15, 30, 18], "value": 18},
    "bars": {"series": [4, 8, 6, 11, 7, 0, 0], "labels": list("LMXJVSD"), "highlight": 4},
    "heatmap": {"values": [0, 1, 2, 3, 4, 0, 2] * 4, "columns": 4},
    "progress": {"value": 62, "target": 100, "unit": "%", "label": "del objetivo", "expected": 70},
    "ring": {"value": 7, "target": 10, "label": "de 10", "expected": 8},
    "streak": {"current": 5, "best": 12},
    "stats": {"stats": [{"label": "Uno", "value": "12"}, {"label": "Dos", "value": "4,5"}]},
    "list": {"rows": [{"label": f"Cosa {i}", "value": f"{i * 3} días"} for i in range(1, 6)]},
    "calendar": {"marked": [3, 6, 8], "today": 6},
    "upnext": {"events": [{"at": _at(i, 9 + i), "title": f"Evento {i}"} for i in range(3)]},
    "shortcuts": {"actions": [{"label": "Desayuno", "href": "/macros/apuntar", "icon": "food"}]},
    "agenda": {
        "entries": [
            {"start": _at(0, 9), "end": _at(0, 10), "title": "Daily", "tone": 1},
            {"start": DAY, "all_day": True, "title": "Cumpleaños", "tone": 7},
        ]
    },
    "week": {"entries": [{"start": _at(i, 10), "title": f"Cosa {i}", "tone": 1} for i in range(4)]},
    "tasks": {
        "tasks": [
            {"id": "00000000-0000-4000-8000-000000000001", "title": "Vencida", "due": "2026-11-04"},
            {"id": "00000000-0000-4000-8000-000000000002", "title": "Hoy", "detail": "a las 10"},
            {"id": "00000000-0000-4000-8000-000000000003", "title": "Hecha", "done": True},
        ],
        "count": 3,
        "checkable": True,
    },
}


def kinds_of(manifest: Path) -> dict[str, str]:
    found = yaml.safe_load(manifest.read_text())
    return {one["id"]: one.get("kind", "kpi") for one in (found.get("ui") or {}).get("widgets", [])}


async def full_panel(module: ModuleType, manifest: Path, monkeypatch) -> list[dict[str, Any]]:
    kinds = kinds_of(manifest)
    envelopes = {
        widget: {"state": "ready", "updated_at": "2026-11-06T17:00:00+00:00", "body": body}
        for widget, kind in kinds.items()
        if (body := SAMPLES.get(kind)) is not None and validate(kind, body) is not None
    }

    async def gather(connection, renderers, ids):
        return {one: envelopes.get(one) for one in ids}

    monkeypatch.setattr(module, "gather", gather)
    return served(await module.build(None))
