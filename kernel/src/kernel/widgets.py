from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.entities import find_matches

KERNEL = "kernel"

COUNT_EVENTS = text("""
    select count(*) as total,
           count(*) filter (where ts >= date_trunc('day', now())) as today,
           count(*) filter (
               where ts >= date_trunc('day', now()) - interval '1 day'
                 and ts <  date_trunc('day', now())
           ) as yesterday
    from kernel.events
""")

EVENTS_PER_DAY = text("""
    select date_trunc('day', ts)::date as day, count(*) as total
    from kernel.events
    where ts >= date_trunc('day', now()) - make_interval(days => :days - 1)
    group by 1
    order by 1
""")

EVENTS_BY_WEEKDAY = text("""
    select extract(isodow from ts)::int as weekday, count(*) as total
    from kernel.events
    group by 1
""")

COUNT_ENTITIES = text("""
    select count(*) filter (where status <> 'merged') as total,
           count(*) filter (
               where status <> 'merged' and created_at >= now() - interval '7 days'
           ) as week
    from kernel.entities
""")

BY_VOLUME = text("""
    select cast(e.id as text) as id, e.name,
           count(v.id) as events
    from kernel.entities e
    cross join lateral kernel.entity_family(e.id) as family(id)
    join kernel.events v on v.entity_id = family.id
    where e.status <> 'merged'
    group by e.id, e.name
    order by count(v.id) desc, e.name
    limit :limit
""")

KINDS: tuple[str, ...] = (
    "kpi",
    "kpi-delta",
    "chart",
    "bars",
    "heatmap",
    "progress",
    "ring",
    "streak",
    "stats",
    "list",
    "calendar",
    "upnext",
    "shortcuts",
    "agenda",
    "week",
    "tasks",
)

LIST_LIKE = frozenset({"list", "upnext", "shortcuts", "calendar", "agenda", "week", "tasks"})


@dataclass(frozen=True)
class Catalogued:
    id: str
    title: str
    hue: int
    kind: str
    sizes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.id}: kind desconocido {self.kind!r}")

    @property
    def shape(self) -> str:
        return "list" if self.kind in LIST_LIKE else "number"


CATALOGUE: tuple[Catalogued, ...] = (
    Catalogued("events", "Eventos", 1, "kpi-delta", ("1x1", "2x2", "2x1", "4x1", "4x2")),
    Catalogued("events_trend", "Actividad", 1, "chart", ("2x2", "2x1", "4x1", "2x4", "4x2", "4x4")),
    Catalogued(
        "events_by_weekday", "Por día de la semana", 5, "bars", ("2x2", "2x1", "4x1", "4x2")
    ),
    Catalogued("activity", "Constancia", 2, "heatmap", ("2x2", "4x1", "4x2", "4x4")),
    Catalogued("entities", "Entidades", 6, "kpi", ("1x1", "1x2", "2x2")),
    Catalogued("entities_by_volume", "Entidades por volumen", 5, "list", ("2x4", "4x2", "4x4")),
    Catalogued("version", "Versión desplegada", 8, "kpi", ("1x1", "2x1", "2x2")),
)

BY_ID = {widget.id: widget for widget in CATALOGUE}


def envelope(state: str, body: Any, uncertainty: dict | None = None) -> dict:
    sealed: dict[str, Any] = {
        "state": state,
        "updated_at": datetime.now(UTC).isoformat(),
        "body": body,
    }
    if uncertainty is not None:
        sealed["uncertainty"] = uncertainty
    return sealed


async def events(connection: AsyncConnection) -> dict:
    row = (await connection.execute(COUNT_EVENTS)).one()
    if row.total == 0:
        return envelope("empty", {"value": 0, "detail": "sin eventos todavía"})
    return envelope(
        "ready",
        {
            "value": row.today,
            "previous": row.yesterday,
            "since": "vs. ayer",
            "good_when": "up",
            "detail": f"{row.total} en total",
        },
    )


def densify(rows: list, days: int) -> list[int]:
    counted = {row.day: row.total for row in rows}
    today = datetime.now(UTC).date()
    return [counted.get(today - timedelta(days=offset), 0) for offset in range(days - 1, -1, -1)]


async def events_trend(connection: AsyncConnection, days: int = 14) -> dict:
    rows = (await connection.execute(EVENTS_PER_DAY, {"days": days})).all()
    series = densify(rows, days)
    if not any(series):
        return envelope("empty", {"series": [], "value": 0})

    return envelope(
        "ready",
        {
            "series": series,
            "value": series[-1],
            "detail": f"últimos {days} días",
        },
    )


async def events_by_weekday(connection: AsyncConnection) -> dict:
    rows = (await connection.execute(EVENTS_BY_WEEKDAY)).all()
    counted = {row.weekday: row.total for row in rows}
    series = [counted.get(day, 0) for day in range(1, 8)]
    if not any(series):
        return envelope("empty", {"series": []})

    today = datetime.now(UTC).isoweekday()
    return envelope(
        "ready",
        {
            "series": series,
            "labels": ["L", "M", "X", "J", "V", "S", "D"],
            "highlight": today - 1,
            "value": series[today - 1],
            "detail": "hoy",
        },
    )


async def activity(connection: AsyncConnection, days: int = 56) -> dict:
    rows = (await connection.execute(EVENTS_PER_DAY, {"days": days})).all()
    series = densify(rows, days)
    if not any(series):
        return envelope("empty", {"values": []})

    active = sum(1 for value in series if value > 0)
    return envelope(
        "ready",
        {
            "values": series,
            "columns": 7,
            "detail": f"{active} de {days} días con actividad",
        },
    )


async def entities(connection: AsyncConnection) -> dict:
    row = (await connection.execute(COUNT_ENTITIES)).one()
    if row.total == 0:
        return envelope("empty", {"value": 0, "detail": "sin entidades todavía"})
    return envelope("ready", {"value": row.total, "detail": f"{row.week} esta semana"})


async def entities_by_volume(connection: AsyncConnection, limit: int = 5) -> dict:
    rows = (await connection.execute(BY_VOLUME, {"limit": limit})).all()
    if not rows:
        return envelope("empty", {"rows": []})

    missing = 0
    labels: list[dict] = []
    for row in rows:
        matches = await find_matches(connection, row.id)
        if matches is None:
            continue
        for candidate in matches.candidates:
            if candidate.would_merge:
                continue
            missing += 1
            labels.append(
                {"entity_id": str(candidate.entity_id), "label": candidate.name, "weight": 1}
            )

    uncertainty = None
    if labels:
        uncertainty = {
            "summary": (
                f"puede faltar: {missing} {'entidad' if missing == 1 else 'entidades'} sin unir"
            ),
            "candidates": labels[:limit],
        }

    return envelope(
        "ready",
        {"rows": [{"label": row.name, "value": f"{row.events} eventos"} for row in rows]},
        uncertainty,
    )


async def version(_: AsyncConnection) -> dict:
    return envelope(
        "ready", {"value": os.environ.get("APP_VERSION", "dev"), "detail": "desplegada"}
    )


RENDERERS = {
    "events": events,
    "events_trend": events_trend,
    "events_by_weekday": events_by_weekday,
    "activity": activity,
    "entities": entities,
    "entities_by_volume": entities_by_volume,
    "version": version,
}
