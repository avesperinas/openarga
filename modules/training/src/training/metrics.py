from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from training import stats, strength, training

APP = "training"
LABEL = 80

SESSION_DAYS = text("select day from training.training_session where ended_at is not null")
ACTIVITY_DAYS = text("select day from training.training_activity")


def _point(key: str, label: str, unit: str, kind: str, day: Any, value: float) -> dict[str, Any]:
    return contracts.metric(
        APP, key=f"{APP}.{key}", label=label, unit=unit, kind=kind, day=day, value=round(value, 1)
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for key, label, query in (
        ("sessions", "Sesiones de fuerza", SESSION_DAYS),
        ("activities", "Actividades", ACTIVITY_DAYS),
    ):
        per_day = Counter(row.day for row in (await connection.execute(query)).all())
        found += [_point(key, label, "count", "amount", day, n) for day, n in per_day.items()]

    analysis = await stats.analyse(connection, training.local_day(datetime.now(UTC)))
    best: dict[tuple[str, Any], float] = {}
    for serie in analysis.series:
        for point in serie.counted:
            at = (serie.variant_id, point.day)
            best[at] = max(best.get(at, 0.0), point.e1rm)
    for (variant_id, day), e1rm in best.items():
        name = analysis.names.get(variant_id)
        if name is None:
            continue
        label = f"Marca estimada · {name.label}"[:LABEL]
        found.append(_point(f"e1rm:{variant_id}", label, "kg", "peak", day, e1rm))
    found += records(analysis)
    return found


def heaviest(entry: strength.Entry) -> float | None:
    loads = [
        (one.weight if entry.load_type == "external" else one.added_load)
        for one in entry.sets
        if one.completed and one.reps
    ]
    loads = [load for load in loads if load]
    return max(loads) if loads else None


def records(analysis: stats.Analysis) -> list[dict]:
    counted = {point.id for serie in analysis.series for point in serie.counted}
    day_best: dict[tuple[str, Any], float] = {}
    days: dict[str, set] = {}
    kinds: dict[str, str] = {}
    for entry in analysis.entries.values():
        days.setdefault(entry.variant_id, set()).add(entry.day)
        kinds[entry.variant_id] = entry.load_type
        load = heaviest(entry) if entry.id in counted else None
        if load is not None:
            at = (entry.variant_id, entry.day)
            day_best[at] = max(day_best.get(at, 0.0), load)
    out: list[dict] = []
    for variant_id, seen in days.items():
        name = analysis.names.get(variant_id)
        if name is None:
            continue
        word = "Peso máximo" if kinds[variant_id] == "external" else "Lastre máximo"
        label = f"{word} · {name.label}"[:LABEL]
        last = None
        for day in sorted(seen):
            value = day_best.get((variant_id, day), last)
            if value is None:
                continue
            last = value
            out.append(_point(f"max:{variant_id}", label, "kg", "peak", day, value))
    return out
