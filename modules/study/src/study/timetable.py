from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_recurrence import Rule, describe, expand, parse, to_rrule
from study import outbox
from study.studies import (
    SESSION_COLUMNS,
    SESSION_FROM,
    Conflict,
    NotFound,
    SessionBrief,
    _clean,
    _link,
    _own,
    session_brief,
)

OPEN_ENDED = timedelta(days=366)
MAX_SESSIONS = 600

UNTOUCHED = """
    not s.touched and s.attendance is null and s.topic is null
    and not exists (select 1 from study.study_note n where n.session_id = s.id)
    and not exists (select 1 from study.study_attachment_link l where l.session_id = s.id)
"""


class ScheduleIn(BaseModel):
    subject_id: str | None = None
    rule: Rule
    starts_on: date
    start_time: time
    end_time: time
    place: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)

    @field_validator("place")
    @classmethod
    def _place(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _link(value)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("la clase tiene que acabar después de empezar")
        if isinstance(self.rule.until, datetime):
            self.rule = self.rule.model_copy(update={"until": self.rule.until.date()})
        if self.rule.until is not None and self.rule.until < self.starts_on:
            raise ValueError("el horario no puede acabar antes de empezar")
        return self


class ScheduleOut(BaseModel):
    id: str
    course_id: str
    subject_id: str | None
    subject: str | None
    rrule: str
    rule: Rule
    phrase: str
    starts_on: date
    ends_on: date | None
    start_time: time
    end_time: time
    place: str | None
    url: str | None
    sessions: int


class SessionIn(BaseModel):
    kind: Literal["class", "tutorial", "event"] = "event"
    title: str | None = Field(default=None, max_length=200)
    subject_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    place: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)

    @field_validator("title", "place")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _link(value)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("la sesión tiene que acabar después de empezar")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("las horas van con su zona")
        if self.kind != "class" and not self.title:
            raise ValueError("una sesión suelta necesita un título")
        return self


class SessionEdit(BaseModel):
    starts_at: datetime
    ends_at: datetime
    place: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    status: Literal["scheduled", "cancelled"] = "scheduled"
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title", "place")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _link(value)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("la clase tiene que acabar después de empezar")
        return self


class AttendanceIn(BaseModel):
    attendance: Literal["present", "absent"] | None


class TopicIn(BaseModel):
    topic: str | None = Field(default=None, max_length=300)

    @field_validator("topic")
    @classmethod
    def _topic(cls, value: str | None) -> str | None:
        return _clean(value)


SCHEDULES = """
    select b.*, j.name as subject, c.tz, c.ends_on as course_ends_on,
           (select count(*) from study.study_session s where s.schedule_id = b.id) as sessions
    from study.study_schedule b
    join study.study_course c on c.id = b.course_id
    left join study.study_subject j on j.id = b.subject_id
"""


def _schedule_out(row) -> ScheduleOut:
    rule = parse(row.rrule)
    until = rule.until
    return ScheduleOut(
        id=str(row.id),
        course_id=str(row.course_id),
        subject_id=str(row.subject_id) if row.subject_id else None,
        subject=row.subject,
        rrule=row.rrule,
        rule=rule,
        phrase=describe(rule),
        starts_on=row.starts_on,
        ends_on=until.date() if isinstance(until, datetime) else until,
        start_time=row.start_time,
        end_time=row.end_time,
        place=row.place,
        url=row.url,
        sessions=row.sessions,
    )


async def schedules(connection: AsyncConnection, course_id: str) -> list[ScheduleOut]:
    await _own(connection, "study_course", course_id)
    rows = (
        await connection.execute(
            text(f"{SCHEDULES} where b.course_id = :id order by b.start_time, b.created_at"),
            {"id": course_id},
        )
    ).all()
    return [_schedule_out(row) for row in rows]


async def schedule(connection: AsyncConnection, schedule_id: str) -> ScheduleOut:
    await _own(connection, "study_schedule", schedule_id)
    row = (
        await connection.execute(text(f"{SCHEDULES} where b.id = :id"), {"id": schedule_id})
    ).one()
    return _schedule_out(row)


async def _check_subject(
    connection: AsyncConnection, course_id: str, subject_id: str | None
) -> None:
    if subject_id is None:
        return
    await _own(connection, "study_subject", subject_id)
    owner = await connection.scalar(
        text("select course_id from study.study_subject where id = :id"), {"id": subject_id}
    )
    if str(owner) != course_id:
        raise Conflict("esa asignatura es de otro estudio")


async def add_schedule(
    connection: AsyncConnection, course_id: str, block: ScheduleIn
) -> ScheduleOut:
    await _own(connection, "study_course", course_id)
    await _check_subject(connection, course_id, block.subject_id)
    schedule_id = str(
        await connection.scalar(
            text("""
                insert into study.study_schedule
                    (course_id, subject_id, rrule, starts_on, start_time, end_time, place, url)
                values (:course_id, :subject_id, :rrule, :starts_on, :start_time, :end_time,
                        :place, :url)
                returning id
            """),
            {**_schedule_params(block), "course_id": course_id},
        )
    )
    await _generate(connection, schedule_id, from_now=False)
    return await schedule(connection, schedule_id)


def _schedule_params(block: ScheduleIn) -> dict:
    return {
        "subject_id": block.subject_id,
        "rrule": to_rrule(block.rule),
        "starts_on": block.starts_on,
        "start_time": block.start_time,
        "end_time": block.end_time,
        "place": block.place,
        "url": block.url,
    }


async def update_schedule(
    connection: AsyncConnection, schedule_id: str, block: ScheduleIn
) -> ScheduleOut:
    await _own(connection, "study_schedule", schedule_id)
    course_id = str(
        await connection.scalar(
            text("select course_id from study.study_schedule where id = :id"), {"id": schedule_id}
        )
    )
    await _check_subject(connection, course_id, block.subject_id)
    await connection.execute(
        text("""
            update study.study_schedule
            set subject_id = :subject_id, rrule = :rrule, starts_on = :starts_on,
                start_time = :start_time, end_time = :end_time, place = :place, url = :url,
                updated_at = now()
            where id = :id
        """),
        {**_schedule_params(block), "id": schedule_id},
    )
    await _generate(connection, schedule_id, from_now=True)
    return await schedule(connection, schedule_id)


async def delete_schedule(connection: AsyncConnection, schedule_id: str) -> int:
    await _own(connection, "study_schedule", schedule_id)
    removed = await _remove_future_untouched(connection, schedule_id)
    await connection.execute(
        text("delete from study.study_schedule where id = :id"), {"id": schedule_id}
    )
    return removed


async def _remove_future_untouched(connection: AsyncConnection, schedule_id: str) -> int:
    rows = (
        await connection.execute(
            text(f"""
                select {SESSION_COLUMNS}, c.tz {SESSION_FROM}
                where s.schedule_id = :id and s.starts_at > now() and {UNTOUCHED}
            """),
            {"id": schedule_id},
        )
    ).all()
    for row in rows:
        await outbox.enqueue(connection, "study.session", outbox.session_payload(row, removed=True))
    if rows:
        await connection.execute(
            text("delete from study.study_session where id = any(cast(:ids as uuid[]))"),
            {"ids": [str(row.id) for row in rows]},
        )
    return len(rows)


async def _generate(connection: AsyncConnection, schedule_id: str, *, from_now: bool) -> int:
    row = (
        await connection.execute(text(f"{SCHEDULES} where b.id = :id"), {"id": schedule_id})
    ).one()
    zone = ZoneInfo(row.tz)
    rule = parse(row.rrule)
    first = datetime.combine(row.starts_on, row.start_time)
    duration = datetime.combine(row.starts_on, row.end_time) - first

    if rule.until is not None:
        last = (
            rule.until
            if isinstance(rule.until, date) and not isinstance(rule.until, datetime)
            else rule.until.date()
        )
        end_day = last + timedelta(days=1)
    elif rule.count is not None:
        end_day = row.starts_on + timedelta(days=366 * 5)
    else:
        end_day = (
            (row.course_ends_on + timedelta(days=1))
            if row.course_ends_on
            else row.starts_on + OPEN_ENDED
        )
    window_start = datetime.combine(row.starts_on, time(0), tzinfo=zone)
    window_end = datetime.combine(end_day, time(0), tzinfo=zone)

    taken: set[date] = set()
    freed: set[date] = set()
    if from_now:
        freed = {
            value.astimezone(zone).date()
            for (value,) in (
                await connection.execute(
                    text(f"""
                        select s.original_start from study.study_session s
                        where s.schedule_id = :id and s.starts_at > now() and {UNTOUCHED}
                    """),
                    {"id": schedule_id},
                )
            ).all()
        }
        await _remove_future_untouched(connection, schedule_id)
        kept = await connection.execute(
            text("select original_start from study.study_session where schedule_id = :id"),
            {"id": schedule_id},
        )
        taken = {value.astimezone(zone).date() for (value,) in kept.all()}
    moment = datetime.now(zone)
    occurrences = expand(rule, first, row.tz, window_start, window_end)[:MAX_SESSIONS]
    created = []
    for occurrence in occurrences:
        start = occurrence.start
        if from_now and ((start <= moment and start.date() not in freed) or start.date() in taken):
            continue
        session_id = await connection.scalar(
            text("""
                insert into study.study_session
                    (course_id, subject_id, schedule_id, original_start, kind, starts_at, ends_at,
                     place, url)
                values (:course_id, :subject_id, :schedule_id, :original, 'class', :start, :end,
                        :place, :url)
                on conflict (schedule_id, original_start) where schedule_id is not null
                do nothing
                returning id
            """),
            {
                "course_id": row.course_id,
                "subject_id": row.subject_id,
                "schedule_id": schedule_id,
                "original": start,
                "start": start,
                "end": start + duration,
                "place": row.place,
                "url": row.url,
            },
        )
        if session_id:
            created.append(str(session_id))
    for session_id in created:
        await outbox.session_changed(connection, session_id)
    return len(created)


class SessionDetail(BaseModel):
    session: SessionBrief
    course_name: str
    subject_name: str | None
    tz: str
    schedule_id: str | None
    phrase: str | None
    touched: bool
    previous_id: str | None
    next_id: str | None


async def sessions(
    connection: AsyncConnection,
    since: datetime,
    until: datetime,
    *,
    course_id: str | None = None,
    subject_id: str | None = None,
) -> list[SessionBrief]:
    where = ["s.starts_at < :until", "s.ends_at > :since"]
    params: dict = {"since": since, "until": until}
    if course_id:
        where.append("s.course_id = cast(:course as uuid)")
        params["course"] = course_id
    if subject_id:
        where.append("s.subject_id = cast(:subject as uuid)")
        params["subject"] = subject_id
    rows = (
        await connection.execute(
            text(
                f"select {SESSION_COLUMNS} {SESSION_FROM} "
                f"where {' and '.join(where)} order by s.starts_at"
            ),
            params,
        )
    ).all()
    return [session_brief(row) for row in rows]


async def course_sessions(
    connection: AsyncConnection, *, course_id: str | None = None, subject_id: str | None = None
) -> list[SessionBrief]:
    field, value = ("s.subject_id", subject_id) if subject_id else ("s.course_id", course_id)
    rows = (
        await connection.execute(
            text(
                f"select {SESSION_COLUMNS} {SESSION_FROM} "
                f"where {field} = cast(:id as uuid) order by s.starts_at"
            ),
            {"id": value},
        )
    ).all()
    return [session_brief(row) for row in rows]


async def session(connection: AsyncConnection, session_id: str) -> SessionDetail:
    await _own(connection, "study_session", session_id)
    row = (
        await connection.execute(
            text(f"""
                select {SESSION_COLUMNS}, c.tz, s.schedule_id, s.touched, b.rrule
                {SESSION_FROM}
                left join study.study_schedule b on b.id = s.schedule_id
                where s.id = :id
            """),
            {"id": session_id},
        )
    ).one()
    siblings = """
        select id from study.study_session
        where {scope} and status = 'scheduled' and starts_at {op} :start
        order by starts_at {order} limit 1
    """
    scope = "subject_id = :scope" if row.subject_id else "course_id = :scope"
    params = {"scope": row.subject_id or row.course_id, "start": row.starts_at}
    previous_id = await connection.scalar(
        text(siblings.format(scope=scope, op="<", order="desc")), params
    )
    next_id = await connection.scalar(
        text(siblings.format(scope=scope, op=">", order="asc")), params
    )
    return SessionDetail(
        session=session_brief(row),
        course_name=row.course,
        subject_name=row.subject,
        tz=row.tz,
        schedule_id=str(row.schedule_id) if row.schedule_id else None,
        phrase=describe(parse(row.rrule)) if row.rrule else None,
        touched=row.touched,
        previous_id=str(previous_id) if previous_id else None,
        next_id=str(next_id) if next_id else None,
    )


async def add_session(
    connection: AsyncConnection, course_id: str, item: SessionIn
) -> SessionDetail:
    await _own(connection, "study_course", course_id)
    await _check_subject(connection, course_id, item.subject_id)
    session_id = str(
        await connection.scalar(
            text("""
                insert into study.study_session
                    (course_id, subject_id, kind, title, starts_at, ends_at, place, url, touched)
                values (:course_id, :subject_id, :kind, :title, :start, :end, :place, :url, true)
                returning id
            """),
            {
                "course_id": course_id,
                "subject_id": item.subject_id,
                "kind": item.kind,
                "title": item.title,
                "start": item.starts_at,
                "end": item.ends_at,
                "place": item.place,
                "url": item.url,
            },
        )
    )
    await outbox.session_changed(connection, session_id)
    return await session(connection, session_id)


async def update_session(
    connection: AsyncConnection, session_id: str, edit: SessionEdit
) -> SessionDetail:
    await _own(connection, "study_session", session_id)
    kind = await connection.scalar(
        text("select kind from study.study_session where id = :id"), {"id": session_id}
    )
    if kind != "class" and not edit.title:
        raise Conflict("una sesión suelta necesita un título")
    await connection.execute(
        text("""
            update study.study_session
            set starts_at = :start, ends_at = :end, place = :place, url = :url, status = :status,
                title = case when kind = 'class' then title else :title end,
                touched = true, updated_at = now()
            where id = :id
        """),
        {
            "start": edit.starts_at,
            "end": edit.ends_at,
            "place": edit.place,
            "url": edit.url,
            "status": edit.status,
            "title": edit.title,
            "id": session_id,
        },
    )
    await outbox.session_changed(connection, session_id, stamp=datetime.now(UTC))
    return await session(connection, session_id)


async def mark_attendance(
    connection: AsyncConnection, session_id: str, given: AttendanceIn
) -> SessionDetail:
    await _own(connection, "study_session", session_id)
    status = await connection.scalar(
        text("select status from study.study_session where id = :id"), {"id": session_id}
    )
    if status == "cancelled" and given.attendance is not None:
        raise Conflict("una clase cancelada no tiene asistencia")
    await connection.execute(
        text("update study.study_session set attendance = :a, updated_at = now() where id = :id"),
        {"a": given.attendance, "id": session_id},
    )
    await outbox.session_changed(connection, session_id)
    return await session(connection, session_id)


async def set_topic(connection: AsyncConnection, session_id: str, given: TopicIn) -> SessionDetail:
    await _own(connection, "study_session", session_id)
    await connection.execute(
        text("update study.study_session set topic = :t, updated_at = now() where id = :id"),
        {"t": given.topic, "id": session_id},
    )
    return await session(connection, session_id)


async def delete_session(connection: AsyncConnection, session_id: str) -> None:
    await _own(connection, "study_session", session_id)
    row = (
        await connection.execute(
            text(f"select {SESSION_COLUMNS}, c.tz, s.schedule_id {SESSION_FROM} where s.id = :id"),
            {"id": session_id},
        )
    ).one()
    if row.schedule_id is not None:
        raise Conflict("una clase del horario se cancela, no se borra")
    await outbox.enqueue(connection, "study.session", outbox.session_payload(row, removed=True))
    await connection.execute(
        text("delete from study.study_session where id = :id"), {"id": session_id}
    )


__all__ = [
    "AttendanceIn",
    "NotFound",
    "ScheduleIn",
    "ScheduleOut",
    "SessionDetail",
    "SessionEdit",
    "SessionIn",
    "TopicIn",
]
