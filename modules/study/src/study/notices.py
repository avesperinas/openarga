from __future__ import annotations

from datetime import time, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from study import studies

KIND = "assessment"
HOUR = time(19, 0)
AHEAD_DAYS = 31


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    today = studies.today()
    found = await studies.assessments(
        connection, pending_only=True, since=today, until=today + timedelta(days=AHEAD_DAYS)
    )
    out = []
    for one in found:
        if one.due_on is None or one.status != "pending":
            continue
        where = one.subject or one.course
        out.append(
            notify.notification(
                KIND,
                f"assessment:{one.id}:{one.due_on.isoformat()}",
                f"Mañana: {one.title}",
                f"/study/estudio/{one.course_id}",
                notify.at(one.due_on - timedelta(days=1), HOUR),
                body=where,
            )
        )
    return out
