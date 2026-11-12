from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

CONTRACT = "metric"


class Metric(BaseModel):
    key: str
    label: str
    unit: str
    kind: Literal["level", "amount", "peak"]
    last_day: date
    last_value: float


POINTS = f"""
    select distinct on (payload->'{CONTRACT}'->>'key', payload->'{CONTRACT}'->>'day')
        payload->'{CONTRACT}'->>'key' as key,
        (payload->'{CONTRACT}'->>'day')::date as day,
        (payload->'{CONTRACT}'->>'value')::float8 as value,
        payload->'{CONTRACT}'->>'label' as label,
        payload->'{CONTRACT}'->>'unit' as unit,
        payload->'{CONTRACT}'->>'kind' as kind
    from goals.events
    where payload ? '{CONTRACT}'
"""

SERIES = text(
    POINTS
    + f"""
      and payload->'{CONTRACT}'->>'key' = :key
      and (payload->'{CONTRACT}'->>'day')::date >= :since
    order by payload->'{CONTRACT}'->>'key', payload->'{CONTRACT}'->>'day', ts desc, ingested_at desc
"""
)

MANY = text(
    POINTS
    + f"""
      and payload->'{CONTRACT}'->>'key' = any(cast(:keys as text[]))
      and (payload->'{CONTRACT}'->>'day')::date >= :since
    order by payload->'{CONTRACT}'->>'key', payload->'{CONTRACT}'->>'day', ts desc, ingested_at desc
"""
)

AVAILABLE = text(f"""
    with points as ({POINTS}
        order by payload->'{CONTRACT}'->>'key', payload->'{CONTRACT}'->>'day', ts desc,
                 ingested_at desc)
    select distinct on (key) key, label, unit, kind, day as last_day, value as last_value
    from points
    order by key, day desc
""")


async def series(connection: AsyncConnection, key: str, since: date) -> dict[date, float]:
    rows = await connection.execute(SERIES, {"key": key, "since": since})
    return {row.day: row.value for row in rows if row.value is not None}


async def series_many(
    connection: AsyncConnection, since_by_key: dict[str, date]
) -> dict[str, dict[date, float]]:
    out: dict[str, dict[date, float]] = {key: {} for key in since_by_key}
    if not since_by_key:
        return out
    rows = await connection.execute(
        MANY, {"keys": list(since_by_key), "since": min(since_by_key.values())}
    )
    for row in rows:
        if row.value is not None and row.day >= since_by_key[row.key]:
            out[row.key][row.day] = row.value
    return out


async def available(connection: AsyncConnection) -> list[Metric]:
    rows = await connection.execute(AVAILABLE)
    found = [
        Metric(
            key=row.key,
            label=row.label or row.key,
            unit=row.unit or "count",
            kind=row.kind if row.kind in ("amount", "peak") else "level",
            last_day=row.last_day,
            last_value=row.last_value,
        )
        for row in rows
        if row.key and row.last_day is not None and row.last_value is not None
    ]
    return sorted(found, key=lambda one: one.label.casefold())


async def find(connection: AsyncConnection, key: str) -> Metric | None:
    for one in await available(connection):
        if one.key == key:
            return one
    return None
