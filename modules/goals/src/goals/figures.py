from __future__ import annotations

import json
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import METRIC, metric
from goals.common import TZ, me

KEY = "goals.tasks_done"
LABEL = "Tareas hechas"

DONE_ON = text(f"""
    select count(*) from goals.goals_task
    where done_by = cast(:me as uuid)
      and (done_at at time zone '{TZ}')::date = :day
""")

ALL_DAYS = text(f"""
    select (done_at at time zone '{TZ}')::date as day, count(*) as n
    from goals.goals_task
    where done_by = cast(:me as uuid)
    group by 1
""")

ENQUEUE = text("""
    insert into goals.goals_outbox (type, payload, dedup_hash)
    values ('goals.metric', cast(:payload as jsonb), :dedup)
    on conflict (user_id, dedup_hash) do nothing
""")


def point(day: date, value: int) -> dict:
    return {
        METRIC: metric(
            "goals", key=KEY, label=LABEL, unit="count", kind="amount", day=day, value=value
        )
    }


async def publish_day(connection: AsyncConnection, day: date) -> None:
    person = me()
    if person is None:
        return
    value = await connection.scalar(DONE_ON, {"me": person, "day": day})
    await connection.execute(
        ENQUEUE,
        {
            "payload": json.dumps(point(day, int(value or 0)), default=str),
            "dedup": f"metric:{KEY}@{day}:{uuid.uuid4().hex}",
        },
    )


async def backfill(connection: AsyncConnection) -> int:
    person = me()
    if person is None:
        return 0
    rows = (await connection.execute(ALL_DAYS, {"me": person})).all()
    for row in rows:
        await connection.execute(
            ENQUEUE,
            {
                "payload": json.dumps(point(row.day, int(row.n)), default=str),
                "dedup": f"metric:{KEY}@{row.day}:history",
            },
        )
    return len(rows)
