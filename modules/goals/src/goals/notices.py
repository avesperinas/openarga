from __future__ import annotations

from datetime import time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from goals import goals
from goals.common import today

KIND = "goals_at_risk"
AT = time(18, 0)
SUNDAY = 6


def _count(value: float | None) -> str:
    if value is None:
        return "0"
    return f"{value:g}"


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    day = today()
    if day.weekday() != SUNDAY:
        return []
    failing = [
        one
        for one in await goals.active(connection)
        if one.kind == "periodic" and one.week_target is not None and one.week_met is False
    ]
    if not failing:
        return []
    monday = day - timedelta(days=6)
    year, week, _ = monday.isocalendar()
    lines = [
        f"{one.title}: {_count(one.week_count)} de {_count(one.week_target)}" for one in failing
    ]
    title = (
        f"«{failing[0].title}» no llega esta semana"
        if len(failing) == 1
        else f"{len(failing)} metas no llegan esta semana"
    )
    return [
        notify.notification(
            KIND,
            f"week:{year}-W{week:02d}",
            title,
            "/goals/metas",
            notify.at(day, AT),
            body=" · ".join(lines),
        )
    ]
