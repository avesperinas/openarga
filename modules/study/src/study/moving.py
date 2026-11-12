from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_agenda import KEY
from study import outbox
from study.studies import Conflict, NotFound, _own


async def move(connection: AsyncConnection, asked: contracts.AgendaMove) -> dict[str, Any]:
    module, kind, object_id = asked.uid.split(":", 2)
    if module != "study" or kind not in ("session", "assessment"):
        raise NotFound(asked.uid)
    now = datetime.now(UTC)
    if kind == "session":
        payload = await _session(connection, object_id, asked, now)
    else:
        payload = await _assessment(connection, object_id, asked, now)
    if payload is None or KEY not in payload:
        raise NotFound(asked.uid)
    return contracts.agenda_moved(payload[KEY])


async def _session(
    connection: AsyncConnection, session_id: str, asked: contracts.AgendaMove, now: datetime
) -> dict[str, Any] | None:
    await _own(connection, "study_session", session_id)
    if asked.all_day:
        raise Conflict("una clase tiene hora")
    if asked.end <= asked.start:
        raise Conflict("la clase tiene que acabar después de empezar")
    await connection.execute(
        text("""
            update study.study_session
            set starts_at = :start, ends_at = :end, touched = true, updated_at = now()
            where id = :id
        """),
        {"start": asked.start, "end": asked.end, "id": session_id},
    )
    return await outbox.session_changed(connection, session_id, stamp=now)


async def _assessment(
    connection: AsyncConnection, assessment_id: str, asked: contracts.AgendaMove, now: datetime
) -> dict[str, Any] | None:
    await _own(connection, "study_assessment", assessment_id)
    tz = await connection.scalar(
        text("""
            select c.tz from study.study_assessment a join study.study_course c on c.id = a.course_id
            where a.id = :id
        """),
        {"id": assessment_id},
    )
    if asked.all_day:
        due_on, due_time = asked.start, None
    else:
        local = asked.start.astimezone(ZoneInfo(tz))
        due_on, due_time = local.date(), local.time().replace(second=0, microsecond=0)
    await connection.execute(
        text("""
            update study.study_assessment
            set due_on = :due_on, due_time = :due_time, updated_at = now()
            where id = :id
        """),
        {"due_on": due_on, "due_time": due_time, "id": assessment_id},
    )
    return await outbox.assessment_changed(connection, assessment_id, stamp=now)


__all__ = ["move"]
