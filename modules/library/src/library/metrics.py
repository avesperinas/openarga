from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from library import stats

APP = "library"


def _point(key: str, label: str, day: date, value: float) -> dict[str, Any]:
    return contracts.metric(
        APP,
        key=f"{APP}.{key}",
        label=label,
        unit="count",
        kind="amount",
        day=day,
        value=round(value, 1),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    rows = (await connection.execute(stats.READ)).all()
    finished = Counter(row.finished_on for row in rows if row.finished_on is not None)
    found = [_point("books_finished", "Libros terminados", day, n) for day, n in finished.items()]
    years = {row.started_on.year for row in rows if row.started_on} | {
        row.finished_on.year for row in rows if row.finished_on
    }
    spread = await asyncio.to_thread(stats.spread_years, rows, years)
    for day, pages in spread.items():
        found.append(_point("pages", "Páginas leídas", date.fromisoformat(day), pages))
    return found
