from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from goals import goals
from goals.common import t

KIND = "goals_at_risk"
AT = time(18, 0)
SUNDAY = 6


def today() -> date:
    return datetime.now(notify.zone()).date()


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
        t(
            "notice.line",
            title=one.title,
            count=_count(one.week_count),
            target=_count(one.week_target),
        )
        for one in failing
    ]
    title = (
        t("notice.one_short", title=failing[0].title)
        if len(failing) == 1
        else t("notice.many_short", count=len(failing))
    )
    return [
        notify.notification(
            KIND,
            f"week:{year}-W{week:02d}",
            title,
            "/goals/goals",
            notify.at(day, AT),
            body=" · ".join(lines),
        )
    ]
