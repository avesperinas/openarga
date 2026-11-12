from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from study import apuntes, studies, timetable

APP = "study"
KINDS = {
    "master": "Máster",
    "degree": "Grado",
    "course": "Curso",
    "certification": "Certificación",
    "language": "Idioma",
    "other": "Estudio",
}
MODALITY = {"in_person": "presencial", "online": "en línea", "hybrid": "mixta"}
STATUS = {
    "planned": "planeado",
    "active": "en curso",
    "finished": "terminado",
    "abandoned": "abandonado",
}
ASSESSMENT = {
    "assignment": "Entrega",
    "exam": "Examen",
    "practical": "Práctica",
    "participation": "Participación",
    "other": "Evaluable",
}
ATTENDANCE = {"present": "fuiste", "absent": "no fuiste"}
BEGINNING = datetime(1970, 1, 1, tzinfo=UTC)
END = datetime(2200, 1, 1, tzinfo=UTC)


def _relative(folder: str) -> str:
    prefix = f"{apuntes.ROOT}/"
    return folder[len(prefix) :] if folder.startswith(prefix) else ""


def _grade(value: float | None, scale: float) -> str:
    return (
        ""
        if value is None
        else write.trimmed(value, 2) + ("" if scale == 10 else f"/{write.trimmed(scale)}")
    )


def course(
    found: studies.CourseDetail,
    folder: str,
    blocks: list[timetable.ScheduleOut],
) -> dict[str, Any]:
    one = found.course
    grades = "grades" in one.tracks
    properties: dict[str, Any] = {
        "clase": KINDS[one.kind].lower(),
        "estado": STATUS[one.status],
        "modalidad": MODALITY[one.modality],
    }
    for name, value in (
        ("centro", one.institution),
        ("inicio", one.starts_on.isoformat() if one.starts_on else None),
        ("fin", one.ends_on.isoformat() if one.ends_on else None),
        ("creditos", one.credits),
        ("horas", one.hours),
        ("nota_media", one.average.average if grades else None),
        ("nota_final", one.final_grade if grades else None),
        (
            "progreso",
            round(one.progress.ratio * 100) if one.progress and "progress" in one.tracks else None,
        ),
        (
            "asistencia",
            round(one.attendance.ratio * 100)
            if one.attendance.ratio is not None and "attendance" in one.tracks
            else None,
        ),
    ):
        if value is not None:
            properties[name] = value
    lead = [KINDS[one.kind]]
    if one.institution:
        lead.append(one.institution)
    lead.append(MODALITY[one.modality])
    lead.append(STATUS[one.status])
    if one.starts_on:
        lead.append(f"desde el {write.long_date(one.starts_on)}")
    if one.progress and "progress" in one.tracks:
        lead.append(one.progress.label)
    subjects = "\n".join(
        f"- {write.link(APP, f'subject:{subject.id}', subject.name)}"
        + (f" · {write.trimmed(subject.credits)} créditos" if subject.credits else "")
        + (f" · {subject.teacher}" if subject.teacher else "")
        + (
            f" · nota {_grade(subject.grade.final, one.scale_max)}"
            if grades and subject.grade.final is not None
            else ""
        )
        for subject in found.subjects
    )
    schedule = "\n".join(
        f"- {block.phrase}"
        + (f" · {block.subject}" if block.subject else "")
        + (f" · {block.place}" if block.place else "")
        for block in blocks
    )
    return contracts.record(
        id=f"course:{one.id}",
        title=one.name,
        kind=KINDS[one.kind],
        href=f"/study/estudio/{one.id}",
        folder=folder,
        properties=properties,
        body=write.sections(
            " · ".join(lead) + ".",
            one.note,
            f"## Asignaturas\n\n{subjects}" if subjects else None,
            f"## Horario\n\n{schedule}" if schedule else None,
            _assessments(found.assessments, one.scale_max, grades),
        ),
    )


def _assessments(found: list[studies.AssessmentOut], scale: float, grades: bool) -> str | None:
    rows = [
        [
            one.title,
            ASSESSMENT[one.kind],
            one.subject or "",
            one.due_on.isoformat() if one.due_on else "",
            {"pending": "pendiente", "submitted": "entregado", "graded": "calificado"}[one.status],
            _grade(one.grade, scale) if grades else "",
        ]
        for one in found
    ]
    if not rows:
        return None
    headers = ["Evaluable", "Clase", "Asignatura", "Fecha", "Estado", "Nota"]
    if not grades:
        headers, rows = headers[:-1], [row[:-1] for row in rows]
    return "## Evaluables\n\n" + write.table(headers, rows)


def subject(
    one: studies.SubjectOut,
    course_: studies.CourseOut,
    folder: str,
    assessments: list[studies.AssessmentOut],
    sessions: list[studies.SessionBrief],
) -> dict[str, Any]:
    grades = "grades" in course_.tracks
    tz = ZoneInfo(course_.tz)
    properties: dict[str, Any] = {"estudio": course_.name, "evaluables": one.assessments}
    for name, value in (
        ("profesor", one.teacher),
        ("creditos", one.credits),
        ("periodo", one.period),
        ("nota", one.grade.final if grades else None),
        ("clases", len(sessions) or None),
    ):
        if value is not None:
            properties[name] = value
    classes = "\n".join(
        f"- {session.starts_at.astimezone(tz):%Y-%m-%d %H:%M}"
        + (f" · {session.topic}" if session.topic else "")
        + (
            f" · {ATTENDANCE[session.attendance]}"
            if session.attendance in ATTENDANCE and "attendance" in course_.tracks
            else ""
        )
        + (" · cancelada" if session.status == "cancelled" else "")
        for session in sessions
    )
    lead = f"De {write.link(APP, f'course:{course_.id}', course_.name)}"
    if one.teacher:
        lead += f", con {one.teacher}"
    if one.credits:
        lead += f", {write.trimmed(one.credits)} créditos"
    return contracts.record(
        id=f"subject:{one.id}",
        title=one.name,
        kind="Asignatura",
        href=f"/study/asignatura/{one.id}",
        folder=folder,
        properties=properties,
        body=write.sections(
            lead + ".",
            one.grade.sentence if grades and one.grade.sentence else None,
            _assessments(assessments, course_.scale_max, grades),
            f"## Clases\n\n{classes}" if classes else None,
        ),
    )


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    places = await apuntes.Places.load(connection)
    found: list[dict[str, Any]] = []
    courses = {one.id: one for one in await studies.courses(connection, "all")}
    for course_id, one in courses.items():
        detail = await studies.course(connection, course_id)
        folder = _relative(places.course_folder(course_id)) or apuntes.clean(one.name)
        blocks = await timetable.schedules(connection, course_id)
        found.append(course(detail, folder, blocks))
        for item in detail.subjects:
            mine = [a for a in detail.assessments if a.subject_id == item.id]
            sessions = await timetable.course_sessions(connection, subject_id=item.id)
            where = (
                _relative(places.subject_folder(item.id)) or f"{folder}/{apuntes.clean(item.name)}"
            )
            found.append(subject(item, one, where, mine, sessions))

    lines: dict[date, list[str]] = defaultdict(list)
    for session in await timetable.sessions(connection, BEGINNING, END):
        owner = courses.get(session.course_id)
        if owner is None or session.status == "cancelled":
            continue
        tz = ZoneInfo(owner.tz)
        start, end = session.starts_at.astimezone(tz), session.ends_at.astimezone(tz)
        target = (
            write.link(APP, f"subject:{session.subject_id}", session.title)
            if session.subject_id
            else write.link(APP, f"course:{session.course_id}", session.course)
        )
        line = f"- Clase: {target} · {start:%H:%M}–{end:%H:%M}"
        if session.topic:
            line += f" · {session.topic}"
        if session.attendance in ATTENDANCE and "attendance" in owner.tracks:
            line += f" · {ATTENDANCE[session.attendance]}"
        lines[start.date()].append(line)
    for course_id, owner in courses.items():
        for one in (await studies.course(connection, course_id)).assessments:
            if one.due_on is None:
                continue
            where = write.link(APP, f"course:{course_id}", owner.name)
            line = f"- {ASSESSMENT[one.kind]}: {one.title} · {where}"
            if one.grade is not None and "grades" in owner.tracks:
                line += f" · nota {_grade(one.grade, owner.scale_max)}"
            lines[one.due_on].append(line)
    for day, told in sorted(lines.items()):
        found.append(
            contracts.record(
                id=f"day:{day.isoformat()}",
                title="Estudios",
                kind="Día",
                href=f"/study/semana?semana={day.isoformat()}",
                day=day,
                body="\n".join(told),
            )
        )
    return found
