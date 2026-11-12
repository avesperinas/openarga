from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_agenda import KEY, dated, uid
from training import training, workouts

TYPE = "training.session"
ACTIVITY_TYPE = "training.activity"

SESSION = text("""
    select s.id, s.started_at, s.ended_at, d.name
    from training.training_session s
    left join training.training_plan_day d on d.id = s.plan_day_id
    where s.id = :id
""")

FINISHED = text("""
    select s.id, s.started_at, s.ended_at, d.name
    from training.training_session s
    left join training.training_plan_day d on d.id = s.plan_day_id
    where s.ended_at is not null
""")


def payload(row, *, cancelled: bool = False) -> dict[str, Any]:
    return {
        KEY: dated(
            uid=uid("training", "session", row.id),
            title=row.name or "Entreno",
            start=row.started_at.astimezone(training.MADRID),
            end=row.ended_at.astimezone(training.MADRID),
            tz="Europe/Madrid",
            status="cancelled" if cancelled else "confirmed",
            href=f"/training/sesion/{row.id}",
        ),
        "session_id": str(row.id),
    }


def _stamped(identity: str, stamp: datetime | None) -> str:
    return identity if stamp is None else f"{identity}:{stamp.isoformat()}"


async def _publish(
    connection: AsyncConnection, row, *, cancelled: bool = False, stamp: datetime | None = None
) -> None:
    status = "cancelled" if cancelled else "confirmed"
    await training.enqueue(
        connection,
        TYPE,
        datetime.now(training.MADRID) if cancelled else row.ended_at,
        payload(row, cancelled=cancelled),
        _stamped(
            f"training:session:{row.id}:agenda:{row.started_at.isoformat()}:"
            f"{row.ended_at.isoformat()}:{status}",
            stamp,
        ),
    )


async def session_changed(
    connection: AsyncConnection, session_id: str, *, stamp: datetime | None = None
) -> dict[str, Any] | None:
    row = (await connection.execute(SESSION, {"id": session_id})).one_or_none()
    if row is not None and row.ended_at is not None:
        await _publish(connection, row, stamp=stamp)
        await workouts.session(connection, row.id)
        return payload(row)
    return None


async def session_row(connection: AsyncConnection, session_id: str):
    return (await connection.execute(SESSION, {"id": session_id})).one_or_none()


async def session_removed(connection: AsyncConnection, row) -> None:
    if row is not None and row.ended_at is not None:
        await _publish(connection, row, cancelled=True)
        await workouts.session(connection, row.id, removed=True, row=row)


async def backfill(connection: AsyncConnection) -> int:
    rows = (await connection.execute(FINISHED)).all()
    for row in rows:
        await _publish(connection, row)
    return len(rows)


ACTIVITIES = text("""
    select a.id, t.name, a.day, a.start_time, a.duration_seconds
    from training.training_activity a join training.training_activity_type t on t.id = a.activity_type_id
""")


def activity_span(activity) -> tuple[datetime, datetime]:
    start = datetime.combine(activity.day, activity.start_time, training.MADRID)
    return start, start + timedelta(seconds=activity.duration_seconds or 3600)


def activity_payload(activity, *, cancelled: bool = False) -> dict[str, Any]:
    start, end = activity_span(activity)
    return {
        KEY: dated(
            uid=uid("training", "activity", activity.id),
            title=activity.name,
            start=start,
            end=end,
            tz="Europe/Madrid",
            status="cancelled" if cancelled else "confirmed",
            href="/training/calendario",
        ),
        "activity_id": str(activity.id),
    }


async def _publish_activity(
    connection: AsyncConnection, activity, *, cancelled: bool = False, stamp: datetime | None = None
) -> None:
    start, end = activity_span(activity)
    status = "cancelled" if cancelled else "confirmed"
    await training.enqueue(
        connection,
        ACTIVITY_TYPE,
        datetime.now(training.MADRID) if cancelled else end,
        activity_payload(activity, cancelled=cancelled),
        _stamped(
            f"training:activity:{activity.id}:agenda:{start.isoformat()}:{end.isoformat()}:{status}",
            stamp,
        ),
    )


async def activity_changed(
    connection: AsyncConnection, activity, *, stamp: datetime | None = None
) -> None:
    await _publish_activity(connection, activity, stamp=stamp)
    await workouts.activity(connection, activity.id)


async def activity_removed(connection: AsyncConnection, activity) -> None:
    await _publish_activity(connection, activity, cancelled=True)
    await workouts.activity(connection, activity.id, removed=True, row=activity)


async def backfill_activities(connection: AsyncConnection) -> int:
    rows = (await connection.execute(ACTIVITIES)).all()
    for row in rows:
        await _publish_activity(connection, row)
    return len(rows)
