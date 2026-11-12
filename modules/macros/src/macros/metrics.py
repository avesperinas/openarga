from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
import arga_nutrients
from macros.common import enqueue

APP = "macros"
WATER = "water_ml"


def figures() -> list[tuple[str, str, str]]:
    out = []
    for one in arga_nutrients.FRONT:
        out.append((one.key, one.name, one.unit))
    out.append((WATER, "Agua bebida", "ml"))
    return out


DAY_ITEMS = text("""
    select i.kind, i.quantity, i.nutrients
    from macros.macros_item i
    join macros.macros_entry e on e.id = i.entry_id
    where e.day = :day and e.status = 'confirmed'
""")

LAST_SENT = text("""
    select distinct on (payload #>> '{metric,key}')
           payload #>> '{metric,key}' as key, (payload #>> '{metric,value}')::float as value
    from macros.macros_outbox
    where type = 'macros.metric' and payload #>> '{metric,day}' = :day
    order by payload #>> '{metric,key}', id desc
""")


async def day_totals(connection: AsyncConnection, day: date) -> dict[str, float]:
    rows = (await connection.execute(DAY_ITEMS, {"day": day})).all()
    total = arga_nutrients.added(*(arga_nutrients.only_known(row.nutrients) for row in rows))
    water = sum(float(row.quantity) for row in rows if row.kind == "water")
    if water:
        total[WATER] = water
    return total


def point(key: str, label: str, unit: str, day: date, value: float) -> dict[str, Any]:
    return contracts.metric(
        APP,
        key=f"{APP}.{key}",
        label=label,
        unit=unit,
        kind="amount",
        day=day,
        value=round(value, 2),
    )


async def refresh(connection: AsyncConnection, days: set[date]) -> int:
    queued = 0
    for day in sorted(days):
        totals = await day_totals(connection, day)
        sent = {
            row.key: row.value
            for row in (await connection.execute(LAST_SENT, {"day": day.isoformat()})).all()
        }
        for key, label, unit in figures():
            full = f"{APP}.{key}"
            if key not in totals and full not in sent:
                continue
            value = round(totals.get(key, 0.0), 2)
            if full in sent and abs(sent[full] - value) < 0.005:
                continue
            found = point(key, label, unit, day, value)
            await enqueue(
                connection,
                "metric",
                {"metric": found},
                dedup=f"metric:{contracts.metric_identity(found)}:{uuid.uuid4().hex}",
            )
            queued += 1
    return queued
