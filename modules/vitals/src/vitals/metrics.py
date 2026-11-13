from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from vitals import body, labs, steps, weight

APP = "vitals"
UNITS = {"bpm": "bpm", "br/min": "br/min", "ml/kg·min": "ml/kg/min", "%": "percent", "": "count"}
LAB_UNITS = {"mg/dL": "mg/dL", "%": "percent", "": "points"}


def _point(key: str, label: str, unit: str, kind: str, day: Any, value: float) -> dict[str, Any]:
    return contracts.metric(
        APP, key=f"{APP}.{key}", label=label, unit=unit, kind=kind, day=day, value=round(value, 2)
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    counted, _ = await steps.read(connection)
    found += [_point("steps", "Steps", "steps", "amount", one.day, one.steps) for one in counted]
    rows = (await connection.execute(weight.ALL)).all()
    found += [
        _point("weight", "Weight", "kg", "level", one.day, one.kg)
        for one in weight.daily([(row.day, float(row.kg)) for row in rows])
    ]
    for found_lab in await labs.evolutions(connection):
        analyte = found_lab.analyte
        unit = LAB_UNITS.get(analyte.unit or "")
        if unit is None:
            continue
        key = "ldl" if analyte.id == "ldl" else f"lab:{analyte.id}"
        by_day = {point.day: point.value for point in found_lab.points}
        found += [
            _point(key, analyte.name, unit, "level", day, value) for day, value in by_day.items()
        ]
    measured = await body.read(connection)
    for metric in body.METRICS:
        unit = UNITS.get(metric.unit, metric.unit)
        if unit not in contracts.UNITS:
            continue
        kind = "amount" if metric.kind == "sum" else "level"
        found += [
            _point(metric.id, metric.name, unit, kind, point.day, point.value)
            for point in measured.get(metric.id, [])
        ]
    return found
