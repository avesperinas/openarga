from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_tenancy import kernel_url, user_headers

MODULE = "training"
CONTRACT = contracts.BODY_WEIGHT

DAYS = text(f"""
    with received as ({contracts.body_weight_days("training.events")})
    select day, kg from received
    union all
    select b.day, b.kg from training.training_bodyweight b
    where not exists (select 1 from received r where r.day = b.day)
    order by day
""")

LATEST = text(f"select kg from ({DAYS.text}) as days order by day desc limit 1")

UNSENT = text(f"""
    with received as ({contracts.body_weight_days("training.events")})
    select b.day, b.kg from training.training_bodyweight b
    where not exists (select 1 from received r where r.day = b.day)
    order by b.day
""")

KEEP = text("""
    insert into training.training_bodyweight (day, kg) values (:day, :kg)
    on conflict (user_id, day) do update set kg = excluded.kg
""")


class WeightIn(BaseModel):
    kg: float = Field(ge=20, le=400)
    day: date | None = None


class Day(BaseModel):
    day: date
    kg: float


class History(BaseModel):
    days: list[Day]
    latest: Day | None
    pending: bool = False


async def history(connection: AsyncConnection) -> History:
    days = [Day(day=row.day, kg=float(row.kg)) for row in (await connection.execute(DAYS)).all()]
    return History(days=days, latest=days[-1] if days else None)


async def keep(connection: AsyncConnection, day: date, kg: float) -> None:
    await connection.execute(KEEP, {"day": day, "kg": round(kg, 2)})


async def ask(client: httpx.AsyncClient, day: date, kg: float) -> dict[str, Any] | None:
    try:
        response = await client.post(
            f"{kernel_url()}/internal/capabilities/{contracts.WEIGHT_LOG}",
            json=contracts.weight_log(kg=kg, day=day),
            headers={**user_headers(), "x-arga-module": MODULE},
            timeout=10.0,
        )
    except httpx.HTTPError:
        return None
    return response.json() if response.status_code == 200 else None


def with_logged(found: History, day: date, kg: float, sent: bool) -> History:
    days = [one for one in found.days if one.day != day] + [Day(day=day, kg=round(kg, 2))]
    days.sort(key=lambda one: one.day)
    return History(days=days, latest=days[-1], pending=not sent)


async def forward(connection: AsyncConnection, client: httpx.AsyncClient) -> int:
    sent = 0
    for row in (await connection.execute(UNSENT)).all():
        if await ask(client, row.day, float(row.kg)) is None:
            break
        sent += 1
    return sent
