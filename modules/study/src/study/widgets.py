from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from study import grades, studies, timetable
from study.studies import LOCAL

KINDS = {"upnext": "upnext", "progress": "progress", "average": "kpi"}
EVENTS = 5


async def _current(connection: AsyncConnection, track: studies.Track) -> studies.CourseOut | None:
    found = [
        c for c in await studies.courses(connection) if c.status == "active" and track in c.tracks
    ]
    return found[0] if found else None


async def upnext(connection: AsyncConnection) -> dict:
    now = datetime.now(LOCAL)
    found = await timetable.sessions(connection, now, now + timedelta(days=14))
    events = [
        (
            s.starts_at,
            s.title,
            " · ".join(filter(None, [s.place, s.course if s.title != s.course else None])),
        )
        for s in found
        if s.status == "scheduled" and s.ends_at > now
    ]
    for item in await studies.assessments(connection, pending_only=True):
        if (
            item.due_on is None
            or item.due_on < now.date()
            or item.due_on > now.date() + timedelta(days=14)
        ):
            continue
        at = datetime.combine(item.due_on, item.due_time or time(23, 59), tzinfo=LOCAL)
        kind = {"exam": "Examen", "assignment": "Entrega"}.get(item.kind, "Evaluable")
        events.append((at, f"{kind}: {item.title}", item.subject or item.course))
    events.sort(key=lambda e: e[0])
    if not events:
        return envelope(KINDS["upnext"], "empty", {"detail": "nada en las dos próximas semanas"})
    return envelope(
        KINDS["upnext"],
        "ready",
        {
            "events": [
                {"at": at.isoformat(), "title": title, "detail": detail or None}
                for at, title, detail in events[:EVENTS]
            ]
        },
    )


async def progress(connection: AsyncConnection) -> dict:
    course = await _current(connection, "progress")
    if course is None:
        return envelope(KINDS["progress"], "empty", {"detail": "ningún estudio en curso"})
    if course.progress is None or course.progress.kind == "time":
        return envelope(
            KINDS["progress"], "empty", {"detail": f"{course.name}: sin créditos ni horas"}
        )
    units = {"credits": "créditos", "hours": "h", "subjects": "asignaturas"}
    return envelope(
        KINDS["progress"],
        "ready",
        {
            "value": course.progress.done,
            "target": course.progress.total,
            "unit": units[course.progress.kind],
            "label": course.name,
        },
    )


async def average(connection: AsyncConnection) -> dict:
    course = await _current(connection, "grades")
    if course is None:
        return envelope(KINDS["average"], "empty", {"detail": "ningún estudio en curso"})
    value = course.average.average
    if value is None and course.grade is not None and course.grade.current is not None:
        value = course.grade.current
    if value is None:
        return envelope(KINDS["average"], "empty", {"detail": f"{course.name}: sin notas todavía"})
    detail = course.name
    if course.average.subjects:
        detail = (
            f"{course.average.counted} de {course.average.subjects} asignaturas · {course.name}"
        )
    return envelope(
        KINDS["average"],
        "ready",
        {"value": grades.number(value, course.scale_max), "icon": "book", "detail": detail},
    )


RENDERERS = {"upnext": upnext, "progress": progress, "average": average}
