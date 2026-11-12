from __future__ import annotations

from datetime import time
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from macros import metrics, summary
from macros.common import today

KIND = "protein"
DEFAULT_AT = time(20, 0)


class Settings(BaseModel):
    protein_at: time = DEFAULT_AT


async def settings(connection: AsyncConnection) -> Settings:
    row = (await connection.execute(text("select protein_at from macros.macros_settings"))).first()
    return Settings(protein_at=row.protein_at) if row else Settings()


async def save(connection: AsyncConnection, wanted: Settings) -> Settings:
    await connection.execute(
        text("""
            insert into macros.macros_settings (protein_at) values (:at)
            on conflict (user_id) do update set protein_at = excluded.protein_at, updated_at = now()
        """),
        {"at": wanted.protein_at.replace(second=0, microsecond=0)},
    )
    return await settings(connection)


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    day = today()
    target = await summary.target_on(connection, day)
    if target is None or not target.protein:
        return []
    eaten = (await metrics.day_totals(connection, day)).get("protein", 0.0)
    if eaten >= target.protein:
        return []
    at = (await settings(connection)).protein_at
    missing = target.protein - eaten
    return [
        notify.notification(
            KIND,
            f"protein:{day.isoformat()}",
            f"Te faltan {missing:.0f} g de proteína",
            "/macros/",
            notify.at(day, at),
            body=f"Llevas {eaten:.0f} g de {target.protein:.0f} g hoy.",
        )
    ]
