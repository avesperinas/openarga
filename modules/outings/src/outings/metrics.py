from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from outings.common import zone
from outings.words import say

APP = "outings"

DONE = text("""
    select (done_at at time zone :tz)::date as day, count(*) as n
    from outings.outings_wish
    where done_at is not null
    group by 1
""")


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    return [
        contracts.metric(
            APP,
            key=f"{APP}.wishes_done",
            label=say("metric.wishes_done"),
            unit="count",
            kind="amount",
            day=row.day,
            value=row.n,
        )
        for row in (await connection.execute(DONE, {"tz": zone().key})).all()
    ]
