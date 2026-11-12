from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope

KIND = "kpi"

LATEST = text("""
    select count(*) as total,
           (select label from __MODULE_ID__.__MODULE_ID___readings order by ts desc limit 1)
             as last_label
    from __MODULE_ID__.__MODULE_ID___readings
""")


async def main(connection: AsyncConnection) -> dict:
    row = (await connection.execute(LATEST)).one()
    if row.total == 0:
        return envelope(KIND, "empty", {"value": 0, "detail": "sin lecturas todavía"})
    return envelope(KIND, "ready", {"value": row.total, "detail": f"última: {row.last_label}"})


RENDERERS = {"main": main}
