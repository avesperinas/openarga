from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from training import training

TYPE = "training.workout"
SESSION = text("""
    select s.id, s.started_at, s.ended_at, s.band_id, d.name
    from training.training_session s
    left join training.training_plan_day d on d.id = s.plan_day_id
    where s.id = :id
""")

SETS = text("""
    select l.confirmed_at, l.reps, l.weight, l.added_load, e.name
    from training.training_set_log l
    join training.training_session_exercise se on se.id = l.session_exercise_id
    join training.training_variant v on v.id = se.variant_id
    join training.training_exercise e on e.id = v.exercise_id
    where se.session_id = :id and l.completed
    order by l.confirmed_at
""")

ACTIVITY = text("""
    select a.id, t.name, a.day, a.start_time, a.duration_seconds, a.band_id, a.ongoing
    from training.training_activity a join training.training_activity_type t on t.id = a.activity_type_id
    where a.id = cast(:id as uuid)
""")


def _number(value) -> str:
    return f"{float(value):g}".replace(".", ",")


def mark_label(row) -> str:
    what = f"{row.reps}" if row.reps is not None else "?"
    if row.weight:
        what += f" × {_number(row.weight)} kg"
    elif row.added_load:
        what += f" + {_number(row.added_load)} kg"
    return f"{row.name} · {what}"[:80]


def _identity(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"training:workout:{payload[contracts.WORKOUT]['id']}:{digest}"


async def _enqueue(connection: AsyncConnection, found: dict[str, Any]) -> None:
    payload = {contracts.WORKOUT: found}
    await training.enqueue(
        connection, TYPE, datetime.fromisoformat(found["end"]), payload, _identity(payload)
    )


async def session(connection: AsyncConnection, session_id, *, removed: bool = False, row=None):
    row = row if removed else (await connection.execute(SESSION, {"id": session_id})).one_or_none()
    if row is None or row.ended_at is None:
        return
    marks = []
    if not removed:
        marks = [
            {"at": one.confirmed_at, "label": mark_label(one)}
            for one in (await connection.execute(SETS, {"id": session_id})).all()
        ][:300]
    await _enqueue(
        connection,
        contracts.workout(
            id=f"training:session:{row.id}",
            kind="strength",
            name=(row.name or "Workout")[:60],
            start=row.started_at.astimezone(training.zone()),
            end=row.ended_at.astimezone(training.zone()),
            tz=training.timezone(),
            href=f"/training/session/{row.id}",
            band_id=None if removed else getattr(row, "band_id", None),
            marks=marks,
            removed=removed,
        ),
    )


def span(activity) -> tuple[datetime, datetime]:
    start = datetime.combine(activity.day, activity.start_time, training.zone())
    return start, start + timedelta(seconds=activity.duration_seconds or 3600)


async def activity(connection: AsyncConnection, activity_id, *, removed: bool = False, row=None):
    if not removed:
        row = (await connection.execute(ACTIVITY, {"id": str(activity_id)})).one_or_none()
        if row is None or row.ongoing:
            return
    start, end = span(row)
    await _enqueue(
        connection,
        contracts.workout(
            id=f"training:activity:{row.id}",
            kind="activity",
            name=row.name[:60],
            start=start,
            end=end,
            tz=training.timezone(),
            href="/training/calendar",
            band_id=None if removed else row.band_id,
            removed=removed,
        ),
    )


async def backfill(connection: AsyncConnection) -> int:
    finished = text("select id from training.training_session where ended_at is not null")
    sessions = (await connection.execute(finished)).all()
    for one in sessions:
        await session(connection, one.id)
    done = (
        await connection.execute(
            text("select id from training.training_activity where not ongoing")
        )
    ).all()
    for one in done:
        await activity(connection, one.id)
    return len(sessions) + len(done)
