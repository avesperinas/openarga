from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module import preferences
from arga_module.i18n import t
from arga_widgets import envelope

CATALOGS = Path(__file__).resolve().parent / "i18n"

KIND = "kpi"

LATEST = text("""
    select count(*) as total,
           (select label from __MODULE_ID__.__MODULE_ID___readings order by ts desc limit 1)
             as last_label
    from __MODULE_ID__.__MODULE_ID___readings
""")


async def main(connection: AsyncConnection) -> dict:
    row = (await connection.execute(LATEST)).one()
    locale = preferences.current().locale
    if row.total == 0:
        return envelope(KIND, "empty", {"value": 0, "detail": t(CATALOGS, "widget.empty", locale)})
    detail = t(CATALOGS, "widget.last", locale, label=row.last_label)
    return envelope(KIND, "ready", {"value": row.total, "detail": detail})


RENDERERS = {"main": main}
