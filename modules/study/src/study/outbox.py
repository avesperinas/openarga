from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_agenda import KEY, dated, uid

ENQUEUE = text("""
    insert into study.study_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :dedup)
    on conflict do nothing
""")


def _default(value: Any) -> str:
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    return str(value)


async def enqueue(
    connection: AsyncConnection,
    type_: str,
    payload: dict[str, Any],
    *,
    stamp: datetime | None = None,
) -> None:
    body = json.dumps(payload, sort_keys=True, default=_default, ensure_ascii=False)
    salt = "" if stamp is None else f"\n{stamp.isoformat()}"
    dedup = hashlib.sha256(f"{type_}\n{body}{salt}".encode()).hexdigest()
    await connection.execute(ENQUEUE, {"type": type_, "payload": body, "dedup": dedup})


KINDS = {"class": "Clase", "tutorial": "Tutoría", "event": "Sesión"}
ASSESSMENTS = {
    "assignment": "Entrega",
    "exam": "Examen",
    "practical": "Práctica",
    "participation": "Participación",
    "other": "Evaluable",
}


LAYER_MAX = 40


def course_layer(name: str) -> str:
    return " ".join(name.split())[:LAYER_MAX].rstrip()


SESSIONS = """
    select s.id, s.course_id, s.subject_id, s.kind, s.title, s.starts_at, s.ends_at,
           s.place, s.status, s.attendance, c.tz, c.name as course, j.name as subject
    from study.study_session s
    join study.study_course c on c.id = s.course_id
    left join study.study_subject j on j.id = s.subject_id
"""

ASSESSMENTS_DUE = """
    select a.id, a.course_id, a.subject_id, a.title, a.kind, a.due_on, a.due_time,
           a.weight, a.status, a.grade, c.tz, c.name as course
    from study.study_assessment a
    join study.study_course c on c.id = a.course_id
"""


async def session_changed(
    connection: AsyncConnection, session_id: str, *, stamp: datetime | None = None
) -> dict[str, Any] | None:
    row = (
        await connection.execute(text(f"{SESSIONS} where s.id = :id"), {"id": session_id})
    ).one_or_none()
    if row is None:
        return None
    payload = session_payload(row)
    await enqueue(connection, "study.session", payload, stamp=stamp)
    return payload


def session_payload(row, *, removed: bool = False) -> dict[str, Any]:
    zone = ZoneInfo(row.tz)
    title = row.title or row.subject or row.course
    return {
        KEY: dated(
            uid=uid("study", "session", row.id),
            title=title,
            start=row.starts_at.astimezone(zone),
            end=row.ends_at.astimezone(zone),
            tz=row.tz,
            location=row.place,
            status="cancelled" if removed or row.status == "cancelled" else "confirmed",
            href=f"/study/clase/{row.id}",
        ),
        "course_id": str(row.course_id),
        "subject_id": str(row.subject_id) if row.subject_id else None,
        "kind": row.kind,
        "attendance": row.attendance,
        "layer": course_layer(row.course),
    }


async def assessment_changed(
    connection: AsyncConnection,
    assessment_id: str,
    *,
    removed: bool = False,
    stamp: datetime | None = None,
) -> dict[str, Any] | None:
    row = (
        await connection.execute(text(f"{ASSESSMENTS_DUE} where a.id = :id"), {"id": assessment_id})
    ).one_or_none()
    if row is None:
        return None
    payload = assessment_payload(row, removed=removed)
    await enqueue(connection, "study.assessment", payload, stamp=stamp)
    return payload


def assessment_payload(row, *, removed: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "course_id": str(row.course_id),
        "subject_id": str(row.subject_id) if row.subject_id else None,
        "kind": row.kind,
        "status": "removed" if removed else row.status,
        "weight": float(row.weight) if row.weight is not None else None,
        "grade": float(row.grade) if row.grade is not None else None,
    }
    if row.due_on is None:
        return payload
    payload["layer"] = course_layer(row.course)
    common = {
        "uid": uid("study", "assessment", row.id),
        "title": f"{ASSESSMENTS.get(row.kind, 'Evaluable')}: {row.title}",
        "tz": row.tz,
        "status": "cancelled" if removed else "confirmed",
        "href": f"/study/evaluable/{row.id}",
    }
    if row.due_time is None:
        payload[KEY] = dated(
            **common, all_day=True, start=row.due_on, end=row.due_on + timedelta(days=1)
        )
    else:
        moment = datetime.combine(row.due_on, row.due_time, tzinfo=ZoneInfo(row.tz))
        payload[KEY] = dated(**common, start=moment, end=moment)
    return payload


async def course_changed(connection: AsyncConnection, course_id: str) -> None:
    row = (
        await connection.execute(
            text("""
                select id, name, kind, institution, status, starts_on, ends_on, credits, hours,
                       closed_on
                from study.study_course where id = :id
            """),
            {"id": course_id},
        )
    ).one_or_none()
    if row is None:
        return
    await enqueue(
        connection,
        "study.course",
        {
            "id": str(row.id),
            "name": row.name,
            "kind": row.kind,
            "institution": row.institution,
            "status": row.status,
            "starts_on": row.starts_on,
            "ends_on": row.ends_on,
            "closed_on": row.closed_on,
            "credits": float(row.credits) if row.credits is not None else None,
            "hours": float(row.hours) if row.hours is not None else None,
        },
    )
    await republish(connection, str(row.id))


async def republish(connection: AsyncConnection, course_id: str | None = None) -> int:
    where = "" if course_id is None else " where c.id = :id"
    params = {} if course_id is None else {"id": course_id}
    count = 0
    for row in (await connection.execute(text(f"{SESSIONS}{where}"), params)).all():
        await enqueue(connection, "study.session", session_payload(row))
        count += 1
    due = " where a.due_on is not null" + ("" if course_id is None else " and c.id = :id")
    for row in (await connection.execute(text(f"{ASSESSMENTS_DUE}{due}"), params)).all():
        await enqueue(connection, "study.assessment", assessment_payload(row))
        count += 1
    return count
