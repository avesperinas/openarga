from __future__ import annotations

import sys
from datetime import date

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_tenancy import kernel_url, user_headers
from macros.common import Unavailable, today

MODULE = "macros"

DOWN = "Salud no contesta ahora: el peso no se ha apuntado. Prueba en un momento."

DAYS = text(f"{contracts.body_weight_days('macros.events')} order by day")


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


async def log(client: httpx.AsyncClient, asked: WeightIn) -> Day:
    try:
        response = await client.post(
            f"{kernel_url()}/internal/capabilities/{contracts.WEIGHT_LOG}",
            json=contracts.weight_log(kg=asked.kg, day=asked.day),
            headers={**user_headers(), "x-arga-module": MODULE},
            timeout=10.0,
        )
    except httpx.HTTPError as error:
        print(f"weight · {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        raise Unavailable(DOWN) from error
    if response.status_code != 200:
        print(f"weight · {response.status_code} {response.text[:300]}", file=sys.stderr, flush=True)
        raise Unavailable(DOWN)
    logged = contracts.WeightLogged.model_validate(response.json())
    return Day(day=logged.day, kg=logged.kg)


def with_logged(found: History, logged: Day) -> History:
    days = sorted(
        [one for one in found.days if one.day != logged.day] + [logged], key=lambda one: one.day
    )
    return History(days=days, latest=days[-1])


__all__ = ["Day", "History", "WeightIn", "history", "log", "today", "with_logged"]
