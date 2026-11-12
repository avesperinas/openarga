from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module import preferences
from training import agenda, plan


def zone() -> ZoneInfo:
    return preferences.current().zone


def timezone() -> str:
    return preferences.current().timezone


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


def local_day(moment: datetime) -> date:
    return moment.astimezone(zone()).date()


def week_bounds(day: date) -> tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


async def enqueue(
    connection: AsyncConnection, type_: str, ts: datetime, payload: dict[str, Any], dedup: str
) -> None:
    await connection.execute(
        text(
            "insert into training.training_outbox (type, ts, payload, dedup_hash) "
            "values (:type, :ts, cast(:payload as jsonb), :dedup) "
            "on conflict (user_id, dedup_hash) do nothing"
        ),
        {"type": type_, "ts": ts, "payload": json.dumps(payload, default=str), "dedup": dedup},
    )


CURRENT_VERSION = text("""
    select v.id
    from training.training_plan p
    join training.training_plan_version v on v.plan_id = p.id
    where p.active and v.published_at is not null
    order by v.number desc
    limit 1
""")

OPEN_ROTATION = text("""
    select id, plan_version_id, number from training.training_rotation where status = 'open'
""")

PENDING_DAYS = text("""
    select d.id, d.name, d.kind, d.position
    from training.training_plan_day d
    where d.plan_version_id = :version_id
      and not exists (
          select 1 from training.training_session s
          where s.plan_day_id = d.id and s.rotation_id = :rotation_id and s.ended_at is not null
      )
    order by d.position
""")

ALL_DAYS = text("""
    select id, name, kind, position from training.training_plan_day
    where plan_version_id = :version_id order by position
""")


class NextSession(BaseModel):
    plan_day_id: str
    name: str
    kind: str
    rotation_number: int
    remaining: int
    days_in_rotation: int


async def next_session(connection: AsyncConnection) -> NextSession | None:
    rotation = (await connection.execute(OPEN_ROTATION)).one_or_none()
    if rotation is not None:
        days = (await connection.execute(ALL_DAYS, {"version_id": rotation.plan_version_id})).all()
        pending = (
            await connection.execute(
                PENDING_DAYS,
                {"version_id": rotation.plan_version_id, "rotation_id": rotation.id},
            )
        ).all()
        if pending:
            first = pending[0]
            return NextSession(
                plan_day_id=str(first.id),
                name=first.name,
                kind=first.kind,
                rotation_number=rotation.number,
                remaining=len(pending),
                days_in_rotation=len(days),
            )

    version_id = await connection.scalar(CURRENT_VERSION)
    if version_id is None:
        return None
    days = (await connection.execute(ALL_DAYS, {"version_id": version_id})).all()
    if not days:
        return None
    last = await connection.scalar(
        text("select coalesce(max(number), 0) from training.training_rotation")
    )
    first = days[0]
    return NextSession(
        plan_day_id=str(first.id),
        name=first.name,
        kind=first.kind,
        rotation_number=last + 1,
        remaining=len(days),
        days_in_rotation=len(days),
    )


class Week(BaseModel):
    done: int
    goal: int
    monday: date


async def week(connection: AsyncConnection, today: date) -> Week:
    monday, sunday = week_bounds(today)
    done = await connection.scalar(
        text(
            "select count(*) from training.training_session "
            "where ended_at is not null and day between :monday and :sunday"
        ),
        {"monday": monday, "sunday": sunday},
    )
    goal = await connection.scalar(text("select weekly_goal from training.training_settings"))
    if goal is None:
        goal = plan.DEFAULT_SETTINGS.weekly_goal
    return Week(done=done, goal=goal, monday=monday)


class Start(BaseModel):
    started_at: datetime | None = None
    gym_id: str | None = None
    plan_day_id: str | None = None
    id: str | None = None


async def start_session(connection: AsyncConnection, request: Start) -> str:
    if request.id is not None:
        found = await connection.scalar(
            text("select id from training.training_session where id = cast(:id as uuid)"),
            {"id": request.id},
        )
        if found is not None:
            return str(found)

    in_progress = await connection.scalar(
        text("select id from training.training_session where ended_at is null")
    )
    if in_progress:
        raise Conflict(f"there is already a session in progress: {in_progress}")

    upcoming = await next_session(connection)
    if upcoming is None:
        raise Conflict("there is no published plan to train")

    rotation = (await connection.execute(OPEN_ROTATION)).one_or_none()
    day_id = upcoming.plan_day_id
    if request.plan_day_id is not None:
        version = rotation.plan_version_id if rotation else await connection.scalar(CURRENT_VERSION)
        chosen = (await connection.execute(ALL_DAYS, {"version_id": version})).all()
        match = next((day for day in chosen if str(day.id) == request.plan_day_id), None)
        if match is None:
            raise Conflict("that day is not part of the current rotation")
        day_id = str(match.id)
        upcoming = upcoming.model_copy(update={"name": match.name, "kind": match.kind})
    if rotation is None:
        version_id = await connection.scalar(CURRENT_VERSION)
        rotation_id = await connection.scalar(
            text(
                "insert into training.training_rotation (plan_version_id, number) "
                "values (:v, :n) returning id"
            ),
            {"v": version_id, "n": upcoming.rotation_number},
        )
        rotation_version = version_id
    else:
        rotation_id, rotation_version = rotation.id, rotation.plan_version_id

    started_at = request.started_at or datetime.now(UTC)
    gym_id = request.gym_id or await default_gym(connection)
    session_id = await connection.scalar(
        text(
            "insert into training.training_session "
            "(id, rotation_id, plan_version_id, plan_day_id, gym_id, day, started_at) "
            "values (coalesce(cast(:id as uuid), gen_random_uuid()), :r, :v, :d, :g, :day, :at) "
            "returning id"
        ),
        {
            "id": request.id,
            "r": rotation_id,
            "v": rotation_version,
            "d": day_id,
            "g": gym_id,
            "day": local_day(started_at),
            "at": started_at,
        },
    )
    await enqueue(
        connection,
        "training.session_started",
        started_at,
        {"session_id": session_id, "day": upcoming.name, "kind": upcoming.kind},
        f"training:session:{session_id}:started",
    )
    return str(session_id)


async def default_gym(connection: AsyncConnection) -> str | None:
    last = await connection.scalar(
        text(
            "select gym_id from training.training_session where gym_id is not null "
            "order by started_at desc limit 1"
        )
    )
    if last:
        return last
    active = (
        await connection.execute(text("select id from training.training_gym where active limit 2"))
    ).all()
    return active[0].id if len(active) == 1 else None


class Finish(BaseModel):
    ended_at: datetime | None = None


async def finish_session(connection: AsyncConnection, session_id: str, request: Finish) -> None:
    session = (
        await connection.execute(
            text(
                "select id, rotation_id, plan_version_id, started_at, ended_at "
                "from training.training_session where id = :id for update"
            ),
            {"id": session_id},
        )
    ).one_or_none()
    if session is None:
        raise NotFound(session_id)
    if session.ended_at is not None:
        return

    ended_at = request.ended_at or datetime.now(UTC)
    if ended_at < session.started_at:
        raise Conflict("a session cannot end before it starts")
    await connection.execute(
        text(
            "update training.training_session set ended_at = :end, duration_seconds = :seconds "
            "where id = :id"
        ),
        {
            "end": ended_at,
            "seconds": int((ended_at - session.started_at).total_seconds()),
            "id": session_id,
        },
    )

    pending = (
        await connection.execute(
            PENDING_DAYS,
            {"version_id": session.plan_version_id, "rotation_id": session.rotation_id},
        )
    ).all()
    if not pending:
        await connection.execute(
            text(
                "update training.training_rotation set status = 'complete', closed_at = :at "
                "where id = :id and status = 'open'"
            ),
            {"at": ended_at, "id": session.rotation_id},
        )

    sets = await connection.scalar(
        text(
            "select count(*) from training.training_set_log l "
            "join training.training_session_exercise e on e.id = l.session_exercise_id "
            "where e.session_id = :id and l.completed"
        ),
        {"id": session_id},
    )
    await enqueue(
        connection,
        "training.session_finished",
        ended_at,
        {
            "session_id": session_id,
            "duration_seconds": int((ended_at - session.started_at).total_seconds()),
            "sets": sets,
            "rotation_closed": not pending,
        },
        f"training:session:{session_id}:finished",
    )
    await agenda.session_changed(connection, session_id)


class Times(BaseModel):
    started_at: datetime
    ended_at: datetime


def _localised(moment: datetime) -> datetime:
    return moment.replace(tzinfo=zone()) if moment.tzinfo is None else moment


async def change_times(connection: AsyncConnection, session_id: str, request: Times) -> None:
    session = (
        await connection.execute(
            text(
                "select rotation_id, started_at, ended_at from training.training_session "
                "where id = :id for update"
            ),
            {"id": session_id},
        )
    ).one_or_none()
    if session is None:
        raise NotFound(session_id)
    if session.ended_at is None:
        raise Conflict("the session is still in progress: correct it once it ends")

    started_at, ended_at = _localised(request.started_at), _localised(request.ended_at)
    if ended_at < started_at:
        raise Conflict("a session cannot end before it starts")
    if ended_at > datetime.now(UTC) + timedelta(minutes=5):
        raise Conflict("a session cannot end in the future")
    if (started_at, ended_at) == (session.started_at, session.ended_at):
        return

    seconds = int((ended_at - started_at).total_seconds())
    await connection.execute(
        text(
            "update training.training_session set started_at = :start, ended_at = :end, "
            "day = :day, duration_seconds = :seconds where id = :id"
        ),
        {
            "start": started_at,
            "end": ended_at,
            "day": local_day(started_at),
            "seconds": seconds,
            "id": session_id,
        },
    )
    await connection.execute(
        text(
            "update training.training_rotation set closed_at = :end "
            "where id = :id and status = 'complete' and closed_at = :before"
        ),
        {"end": ended_at, "id": session.rotation_id, "before": session.ended_at},
    )
    now = datetime.now(UTC)
    await enqueue(
        connection,
        "training.session_times_changed",
        now,
        {
            "session_id": session_id,
            "started_at": started_at.astimezone(UTC).isoformat(),
            "ended_at": ended_at.astimezone(UTC).isoformat(),
            "duration_seconds": seconds,
        },
        f"training:session:{session_id}:times:{now.isoformat()}",
    )
    await agenda.session_changed(connection, session_id, stamp=now)


class Deleted(BaseModel):
    session_id: str
    sets: int


async def delete_session(
    connection: AsyncConnection, session_id: str, with_sets: bool = False
) -> Deleted:
    row = (
        await connection.execute(
            text(
                "select s.rotation_id, s.plan_version_id, s.source, "
                "(select count(*) from training.training_session_exercise e "
                " join training.training_set_log l on l.session_exercise_id = e.id "
                " where e.session_id = s.id) as sets "
                "from training.training_session s where s.id = :id for update"
            ),
            {"id": session_id},
        )
    ).one_or_none()
    if row is None:
        raise NotFound(session_id)
    if row.sets and not with_sets:
        raise Conflict(f"the workout has {row.sets} sets; confirm you want to delete them")

    calendar = await agenda.session_row(connection, session_id)
    await connection.execute(
        text("delete from training.training_session where id = :id"), {"id": session_id}
    )

    rotation = (
        await connection.execute(
            text(
                "select r.id, r.status, r.number, "
                "(select count(*) from training.training_session s "
                " where s.rotation_id = r.id) as sessions, "
                "(select max(number) from training.training_rotation) as last "
                "from training.training_rotation r where r.id = :id for update"
            ),
            {"id": row.rotation_id},
        )
    ).one()
    if rotation.sessions == 0 and rotation.number == rotation.last:
        await connection.execute(
            text("delete from training.training_rotation where id = :id"), {"id": rotation.id}
        )
    elif rotation.status == "complete":
        pending = (
            await connection.execute(
                PENDING_DAYS, {"version_id": row.plan_version_id, "rotation_id": rotation.id}
            )
        ).all()
        if pending:
            other_open = await connection.scalar(
                text(
                    "select 1 from training.training_rotation where status = 'open' and id <> :id"
                ),
                {"id": rotation.id},
            )
            reopen = rotation.number == rotation.last and not other_open
            await connection.execute(
                text(
                    "update training.training_rotation set status = :status, closed_at = "
                    "case when :status = 'open' then null else closed_at end where id = :id"
                ),
                {"status": "open" if reopen else "abandoned", "id": rotation.id},
            )

    await enqueue(
        connection,
        "training.session_deleted",
        datetime.now(UTC),
        {"session_id": session_id, "sets": row.sets, "source": row.source},
        f"training:session:{session_id}:deleted",
    )
    await agenda.session_removed(connection, calendar)
    return Deleted(session_id=session_id, sets=row.sets)


class RotationDay(BaseModel):
    plan_day_id: str
    name: str
    kind: str
    done: bool


class Rotation(BaseModel):
    number: int
    open: bool
    days: list[RotationDay]


async def rotation(connection: AsyncConnection) -> Rotation | None:
    current = (await connection.execute(OPEN_ROTATION)).one_or_none()
    if current is not None:
        days = (await connection.execute(ALL_DAYS, {"version_id": current.plan_version_id})).all()
        pending = {
            row.id
            for row in (
                await connection.execute(
                    PENDING_DAYS,
                    {"version_id": current.plan_version_id, "rotation_id": current.id},
                )
            ).all()
        }
        return Rotation(
            number=current.number,
            open=True,
            days=[
                RotationDay(
                    plan_day_id=str(day.id),
                    name=day.name,
                    kind=day.kind,
                    done=day.id not in pending,
                )
                for day in days
            ],
        )
    version_id = await connection.scalar(CURRENT_VERSION)
    if version_id is None:
        return None
    days = (await connection.execute(ALL_DAYS, {"version_id": version_id})).all()
    last = await connection.scalar(
        text("select coalesce(max(number), 0) from training.training_rotation")
    )
    return Rotation(
        number=last + 1,
        open=False,
        days=[
            RotationDay(plan_day_id=str(day.id), name=day.name, kind=day.kind, done=False)
            for day in days
        ],
    )


class SessionSummary(BaseModel):
    id: str
    day: date
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    day_name: str
    kind: str
    rotation_number: int
    gym: str | None
    exercises: int
    sets: int


async def sessions_between(
    connection: AsyncConnection, first: date, last: date
) -> list[SessionSummary]:
    rows = (
        await connection.execute(
            text(
                "select s.id, s.day, s.started_at, s.ended_at, s.duration_seconds, "
                "d.name as day_name, d.kind, r.number as rotation_number, g.name as gym, "
                "(select count(distinct e.id) from training.training_session_exercise e "
                " join training.training_set_log l on l.session_exercise_id = e.id "
                " where e.session_id = s.id and l.completed) as exercises, "
                "(select count(*) from training.training_session_exercise e "
                " join training.training_set_log l on l.session_exercise_id = e.id "
                " where e.session_id = s.id and l.completed) as sets "
                "from training.training_session s "
                "join training.training_plan_day d on d.id = s.plan_day_id "
                "join training.training_rotation r on r.id = s.rotation_id "
                "left join training.training_gym g on g.id = s.gym_id "
                "where s.day between :first and :last "
                "order by s.started_at desc"
            ),
            {"first": first, "last": last},
        )
    ).all()
    return [
        SessionSummary(
            id=str(row.id),
            day=row.day,
            started_at=row.started_at,
            ended_at=row.ended_at,
            duration_seconds=row.duration_seconds,
            day_name=row.day_name,
            kind=row.kind,
            rotation_number=row.rotation_number,
            gym=row.gym,
            exercises=row.exercises,
            sets=row.sets,
        )
        for row in rows
    ]


class ExerciseIn(BaseModel):
    variant_id: str
    plan_slot_id: str | None = None


async def add_exercise(connection: AsyncConnection, session_id: str, request: ExerciseIn) -> str:
    exists = await connection.scalar(
        text("select 1 from training.training_session where id = :id"), {"id": session_id}
    )
    if not exists:
        raise NotFound(session_id)
    found = await connection.scalar(
        text(
            "select id from training.training_session_exercise where session_id = :s "
            "and plan_slot_id is not distinct from :slot and variant_id = :v "
            "and plan_slot_id is not null"
        ),
        {"s": session_id, "slot": request.plan_slot_id, "v": request.variant_id},
    )
    if found:
        return str(found)
    exercise_id = await connection.scalar(
        text(
            "insert into training.training_session_exercise "
            "(session_id, plan_slot_id, variant_id, position) "
            "values (:s, :slot, :v, (select coalesce(max(position), 0) + 1 "
            "from training.training_session_exercise where session_id = :s)) returning id"
        ),
        {"s": session_id, "slot": request.plan_slot_id, "v": request.variant_id},
    )
    return str(exercise_id)


async def put_exercise(
    connection: AsyncConnection, session_id: str, exercise_id: str, request: ExerciseIn
) -> str:
    exists = await connection.scalar(
        text("select 1 from training.training_session where id = :id"), {"id": session_id}
    )
    if not exists:
        raise NotFound(session_id)
    current = (
        await connection.execute(
            text(
                "select session_id, plan_slot_id, variant_id from training.training_session_exercise "
                "where id = :id"
            ),
            {"id": exercise_id},
        )
    ).one_or_none()
    if current is not None:
        same = (
            str(current.session_id) == session_id
            and str(current.variant_id) == request.variant_id
            and (str(current.plan_slot_id) if current.plan_slot_id else None)
            == request.plan_slot_id
        )
        if not same:
            raise Conflict(f"exercise {exercise_id} already exists with different data")
        return exercise_id
    if request.plan_slot_id is not None:
        found = await connection.scalar(
            text(
                "select id from training.training_session_exercise where session_id = :s "
                "and plan_slot_id = :slot and variant_id = :v"
            ),
            {"s": session_id, "slot": request.plan_slot_id, "v": request.variant_id},
        )
        if found:
            return str(found)
    await connection.execute(
        text(
            "insert into training.training_session_exercise "
            "(id, session_id, plan_slot_id, variant_id, position) "
            "values (:id, :s, :slot, :v, (select coalesce(max(position), 0) + 1 "
            "from training.training_session_exercise where session_id = :s))"
        ),
        {"id": exercise_id, "s": session_id, "slot": request.plan_slot_id, "v": request.variant_id},
    )
    return exercise_id


class NotesIn(BaseModel):
    notes: Annotated[str, Field(max_length=2000)] | None = None


async def set_exercise_notes(
    connection: AsyncConnection, session_id: str, exercise_id: str, request: NotesIn
) -> str | None:
    notes = (request.notes or "").strip() or None
    updated = await connection.scalar(
        text(
            "update training.training_session_exercise set notes = :notes "
            "where id = :id and session_id = :session returning id"
        ),
        {"notes": notes, "id": exercise_id, "session": session_id},
    )
    if updated is None:
        raise NotFound(exercise_id)
    return notes


class SetIn(BaseModel):
    reps: int | None = Field(default=None, ge=0, le=200)
    weight: Decimal | None = Field(default=None, ge=0, max_digits=6, decimal_places=2)
    added_load: Decimal | None = Field(default=None, ge=0, max_digits=6, decimal_places=2)
    completed: bool = True
    confirmed_at: datetime

    @model_validator(mode="after")
    def _completed_has_reps(self) -> SetIn:
        if self.completed and self.reps is None:
            raise ValueError("a completed set has reps")
        return self


class SetOut(BaseModel):
    id: str
    number: int
    revision: int
    created: bool


SET_FIELDS = ("reps", "weight", "added_load", "completed", "confirmed_at")


async def put_set(
    connection: AsyncConnection, session_id: str, exercise_id: str, number: int, request: SetIn
) -> SetOut:
    owner = await connection.scalar(
        text("select session_id from training.training_session_exercise where id = :id"),
        {"id": exercise_id},
    )
    if owner is None or str(owner) != session_id:
        raise NotFound(exercise_id)

    values = request.model_dump()
    current = (
        await connection.execute(
            text(
                "select id, reps, weight, added_load, completed, confirmed_at, revision "
                "from training.training_set_log where session_exercise_id = :e and number = :n for update"
            ),
            {"e": exercise_id, "n": number},
        )
    ).one_or_none()

    if current is None:
        row = (
            await connection.execute(
                text(
                    "insert into training.training_set_log "
                    "(session_exercise_id, number, reps, weight, added_load, completed, "
                    "confirmed_at) "
                    "values (:e, :n, :reps, :weight, :added_load, :completed, :confirmed_at) "
                    "on conflict (session_exercise_id, number) do nothing "
                    "returning id, revision"
                ),
                {"e": exercise_id, "n": number, **values},
            )
        ).one_or_none()
        if row is None:
            return await put_set(connection, session_id, exercise_id, number, request)
        created, set_id, revision = True, row.id, row.revision
    else:
        same = all(_same(getattr(current, field), values[field]) for field in SET_FIELDS)
        if same:
            return SetOut(
                id=str(current.id), number=number, revision=current.revision, created=False
            )
        revision = current.revision + 1
        await connection.execute(
            text(
                "update training.training_set_log set reps = :reps, weight = :weight, "
                "added_load = :added_load, completed = :completed, confirmed_at = :confirmed_at, "
                "revision = :revision, updated_at = now() where id = :id"
            ),
            {**values, "revision": revision, "id": current.id},
        )
        created, set_id = False, current.id

    variant = await connection.scalar(
        text("select variant_id from training.training_session_exercise where id = :id"),
        {"id": exercise_id},
    )
    await enqueue(
        connection,
        "training.set_logged",
        request.confirmed_at,
        {
            "session_id": session_id,
            "variant_id": variant,
            "number": number,
            "revision": revision,
            **{key: values[key] for key in ("reps", "weight", "added_load", "completed")},
        },
        f"training:set:{set_id}:{revision}",
    )
    return SetOut(id=str(set_id), number=number, revision=revision, created=created)


def _same(stored: Any, sent: Any) -> bool:
    if isinstance(stored, Decimal) or isinstance(sent, Decimal):
        return (stored is None and sent is None) or (
            stored is not None and sent is not None and Decimal(stored) == Decimal(sent)
        )
    return stored == sent


class SetView(BaseModel):
    number: int
    reps: int | None
    weight: float | None
    added_load: float | None
    completed: bool
    confirmed_at: datetime


class ExerciseView(BaseModel):
    id: str
    plan_slot_id: str | None
    variant_id: str
    variant: str
    position: int
    notes: str | None = None
    sets: list[SetView]


class LastTime(BaseModel):
    variant_id: str
    day: date
    gym_id: str | None = None
    gym: str | None = None
    sets: list[SetView]


class SessionView(BaseModel):
    id: str
    rotation_number: int
    plan_day_id: str
    day_name: str
    kind: str
    day: date
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    gym_id: str | None
    source: str = "app"
    slots: list[plan.Slot]
    exercises: list[ExerciseView]
    history: list[LastTime]


async def read_session(connection: AsyncConnection, session_id: str) -> SessionView:
    head = (
        await connection.execute(
            text(
                "select s.id, r.number as rotation_number, s.plan_day_id, s.plan_version_id, "
                "d.name as day_name, "
                "d.kind, s.day, s.started_at, s.ended_at, s.duration_seconds, s.gym_id, s.source "
                "from training.training_session s "
                "join training.training_rotation r on r.id = s.rotation_id "
                "join training.training_plan_day d on d.id = s.plan_day_id "
                "where s.id = :id"
            ),
            {"id": session_id},
        )
    ).one_or_none()
    if head is None:
        raise NotFound(session_id)

    rows = (
        await connection.execute(
            text(
                "select e.id, e.plan_slot_id, e.variant_id, v.name as variant, e.position, "
                "e.notes, l.number, l.reps, l.weight, l.added_load, l.completed, l.confirmed_at "
                "from training.training_session_exercise e "
                "join training.training_variant v on v.id = e.variant_id "
                "left join training.training_set_log l on l.session_exercise_id = e.id "
                "where e.session_id = :id order by e.position, l.number"
            ),
            {"id": session_id},
        )
    ).all()
    exercises: dict[str, ExerciseView] = {}
    for row in rows:
        exercise = exercises.setdefault(
            str(row.id),
            ExerciseView(
                id=str(row.id),
                plan_slot_id=str(row.plan_slot_id) if row.plan_slot_id else None,
                variant_id=str(row.variant_id),
                variant=row.variant,
                position=row.position,
                notes=row.notes,
                sets=[],
            ),
        )
        if row.number is not None:
            exercise.sets.append(
                SetView(
                    number=row.number,
                    reps=row.reps,
                    weight=float(row.weight) if row.weight is not None else None,
                    added_load=float(row.added_load) if row.added_load is not None else None,
                    completed=row.completed,
                    confirmed_at=row.confirmed_at,
                )
            )

    slots = await plan.day_slots(connection, str(head.plan_version_id), str(head.plan_day_id))
    variants = dict.fromkeys(
        [option.variant_id for slot in slots for option in slot.options]
        + [exercise.variant_id for exercise in exercises.values()]
    )
    gym_id = str(head.gym_id) if head.gym_id else None
    history = [
        found
        for variant in variants
        if (found := await last_time(connection, variant, session_id, gym_id)) is not None
    ]

    return SessionView(
        id=str(head.id),
        rotation_number=head.rotation_number,
        plan_day_id=str(head.plan_day_id),
        day_name=head.day_name,
        kind=head.kind,
        day=head.day,
        started_at=head.started_at,
        ended_at=head.ended_at,
        duration_seconds=head.duration_seconds,
        gym_id=str(head.gym_id) if head.gym_id else None,
        source=head.source,
        slots=slots,
        exercises=list(exercises.values()),
        history=history,
    )


async def in_progress(connection: AsyncConnection) -> str | None:
    found = await connection.scalar(
        text("select id from training.training_session where ended_at is null")
    )
    return str(found) if found else None


async def last_time(
    connection: AsyncConnection,
    variant_id: str,
    before_session: str | None = None,
    gym_id: str | None = None,
) -> LastTime | None:
    session = (
        await connection.execute(
            text(
                "select e.id, s.day, s.gym_id, g.name as gym from training.training_session_exercise e "
                "join training.training_session s on s.id = e.session_id "
                "left join training.training_gym g on g.id = s.gym_id "
                "where e.variant_id = :v and s.ended_at is not null "
                "and (cast(:before as uuid) is null or s.id <> cast(:before as uuid)) "
                "and exists (select 1 from training.training_set_log l "
                "            where l.session_exercise_id = e.id and l.completed) "
                "order by coalesce(s.gym_id = cast(:gym as uuid), false) desc, "
                "s.started_at desc limit 1"
            ),
            {"v": variant_id, "before": before_session, "gym": gym_id},
        )
    ).one_or_none()
    if session is None:
        return None
    sets = (
        await connection.execute(
            text(
                "select number, reps, weight, added_load, completed, confirmed_at "
                "from training.training_set_log where session_exercise_id = :e order by number"
            ),
            {"e": session.id},
        )
    ).all()
    return LastTime(
        variant_id=variant_id,
        day=session.day,
        gym_id=str(session.gym_id) if session.gym_id else None,
        gym=session.gym,
        sets=[
            SetView(
                number=row.number,
                reps=row.reps,
                weight=float(row.weight) if row.weight is not None else None,
                added_load=float(row.added_load) if row.added_load is not None else None,
                completed=row.completed,
                confirmed_at=row.confirmed_at,
            )
            for row in sets
        ],
    )
