from __future__ import annotations

import json
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

MODULE = "__MODULE_ID__"
EVENT = f"{MODULE}.reading"


class NotFound(Exception):
    pass


class ReadingIn(BaseModel):
    label: str = Field(min_length=1, max_length=40, description="La etiqueta, p. ej. `peso`.")
    value: float = Field(description="El valor medido.")
    ts: AwareDatetime | None = Field(default=None, description="Cuándo; ahora si no se dice.")


class Reading(BaseModel):
    id: str
    ts: datetime
    label: str
    value: float


class TargetIn(BaseModel):
    label: str = Field(min_length=1, max_length=40, description="La etiqueta, p. ej. `peso`.")
    value: float = Field(description="El valor al que se quiere llegar.")


class Target(BaseModel):
    label: str
    value: float


INSERT = text("""
    insert into __MODULE_ID__.__MODULE_ID___readings (ts, label, value)
    values (coalesce(:ts, now()), :label, :value)
    returning id::text as id, ts, label, value
""")

ENQUEUE = text("""
    insert into __MODULE_ID__.__MODULE_ID___outbox (type, ts, payload, dedup_hash)
    values (:type, :ts, cast(:payload as jsonb), :dedup_hash)
""")

LIST = text("""
    select id::text as id, ts, label, value
    from __MODULE_ID__.__MODULE_ID___readings
    where cast(:label as text) is null or label = cast(:label as text)
    order by ts desc
    limit :limit
""")

TARGETS = text("select label, value from __MODULE_ID__.__MODULE_ID___targets order by label")

UPSERT_TARGET = text("""
    insert into __MODULE_ID__.__MODULE_ID___targets (label, value, updated_at)
    values (:label, :value, now())
    on conflict (user_id, label) do update set value = excluded.value, updated_at = now()
    returning label, value
""")


def _reading(row) -> Reading:
    return Reading(id=row.id, ts=row.ts, label=row.label, value=float(row.value))


async def add(connection: AsyncConnection, reading: ReadingIn) -> Reading:
    row = (
        await connection.execute(
            INSERT, {"ts": reading.ts, "label": reading.label, "value": reading.value}
        )
    ).one()
    found = _reading(row)
    await connection.execute(
        ENQUEUE,
        {
            "type": EVENT,
            "ts": found.ts,
            "payload": json.dumps({"label": found.label, "value": found.value}),
            "dedup_hash": f"reading:{found.id}",
        },
    )
    return found


async def list_readings(
    connection: AsyncConnection, label: str | None = None, limit: int = 30
) -> list[Reading]:
    rows = (await connection.execute(LIST, {"label": label, "limit": limit})).all()
    return [_reading(row) for row in rows]


async def targets(connection: AsyncConnection) -> list[Target]:
    rows = (await connection.execute(TARGETS)).all()
    return [Target(label=row.label, value=float(row.value)) for row in rows]


async def set_target(connection: AsyncConnection, target: TargetIn) -> Target:
    row = (
        await connection.execute(UPSERT_TARGET, {"label": target.label, "value": target.value})
    ).one()
    return Target(label=row.label, value=float(row.value))
