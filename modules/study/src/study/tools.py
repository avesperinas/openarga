from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, Self
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_recurrence import Rule
from study import apuntes, notes, studies, timetable
from study.studies import LOCAL

MODULE = "study"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _grade(grade) -> dict[str, Any]:
    return {
        "verdict": grade.verdict,
        "graded_average": grade.current,
        "secured": grade.secured,
        "graded_weight_percent": grade.graded_weight,
        "remaining_weight_percent": grade.remaining_weight,
        "needed_to_pass": grade.needed_to_pass,
        "needed_for_target": grade.needed_for_target,
        "final": grade.final,
        "final_is_record": grade.final_source == "record",
        "summary": grade.sentence,
    }


def _course(one: studies.CourseOut) -> dict[str, Any]:
    return {
        "course_id": one.id,
        "name": one.name,
        "kind": one.kind,
        "institution": one.institution,
        "status": one.status,
        "starts_on": one.starts_on.isoformat() if one.starts_on else None,
        "ends_on": one.ends_on.isoformat() if one.ends_on else None,
        "scale": f"0-{one.scale_max:g}, pass {one.pass_mark:g}",
        "target_grade": one.target_grade,
        "tracks": one.tracks,
        "average": one.average.average if "grades" in one.tracks else None,
        "progress": one.progress.label if one.progress and "progress" in one.tracks else None,
        "attendance": (
            f"{one.attendance.present} of {one.attendance.present + one.attendance.absent} marked"
            if one.attendance.present + one.attendance.absent and "attendance" in one.tracks
            else None
        ),
        "campus_url": one.campus_url,
        "modality": one.modality,
        "credits": one.credits,
        "hours": one.hours,
        "tone": one.tone,
        "note": one.note,
        "final_grade": one.final_grade,
        "closed_on": one.closed_on.isoformat() if one.closed_on else None,
    }


def _session(one: studies.SessionBrief) -> dict[str, Any]:
    return {
        "session_id": one.id,
        "course": one.course,
        "title": one.title,
        "kind": one.kind,
        "starts_at": one.starts_at.astimezone(LOCAL).isoformat(),
        "ends_at": one.ends_at.astimezone(LOCAL).isoformat(),
        "place": one.place,
        "url": one.url,
        "status": one.status,
        "attendance": one.attendance,
        "topic": one.topic,
        "has_notes": one.has_notes,
    }


def _assessment(one: studies.AssessmentOut) -> dict[str, Any]:
    return {
        "assessment_id": one.id,
        "course": one.course,
        "subject": one.subject,
        "title": one.title,
        "kind": one.kind,
        "due_on": one.due_on.isoformat() if one.due_on else None,
        "due_time": one.due_time.isoformat(timespec="minutes") if one.due_time else None,
        "days_left": one.days_left,
        "weight_percent": one.weight,
        "min_grade": one.min_grade,
        "status": one.status,
        "grade": one.grade,
    }


class GetCourses(BaseModel):
    scope: Literal["current", "archive", "all"] = Field(
        default="current",
        description="current: en curso y planeados; archive: terminados y abandonados.",
    )


async def get_courses(connection: AsyncConnection, arguments: GetCourses) -> dict[str, Any]:
    found = await studies.courses(connection, arguments.scope)
    result = []
    for one in found:
        detail = await studies.course(connection, one.id)
        result.append(
            {
                **_course(one),
                "subjects": [
                    {
                        "subject_id": s.id,
                        "name": s.name,
                        "credits": s.credits,
                        "period": s.period,
                        "verdict": s.grade.verdict,
                        "final": s.grade.final,
                    }
                    for s in detail.subjects
                ],
            }
        )
    return {"courses": result}


class GetWeek(BaseModel):
    since: date | None = Field(default=None, description="Primer día; hoy si no se dice.")
    until: date | None = Field(
        default=None, description="Último día incluido; una semana después del primero si no."
    )


async def get_week(connection: AsyncConnection, arguments: GetWeek) -> dict[str, Any]:
    first = arguments.since or studies.today()
    last = arguments.until or first + timedelta(days=6)
    if last < first:
        raise studies.Conflict("el último día va después del primero")
    start = datetime.combine(first, time(0), tzinfo=LOCAL)
    end = datetime.combine(last + timedelta(days=1), time(0), tzinfo=LOCAL)
    found = await timetable.sessions(connection, start, end)
    due = await studies.assessments(connection, since=first, until=last + timedelta(days=1))
    return {
        "from": first.isoformat(),
        "to": last.isoformat(),
        "sessions": [_session(one) for one in found],
        "assessments": [_assessment(one) for one in due],
    }


class GetGrades(BaseModel):
    course_id: UUID | None = Field(default=None, description="El estudio, de get_courses.")
    subject_id: UUID | None = Field(default=None, description="O una asignatura sola.")

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.course_id is None) == (self.subject_id is None):
            raise ValueError("di el estudio o la asignatura, uno de los dos")
        return self


async def get_grades(connection: AsyncConnection, arguments: GetGrades) -> dict[str, Any]:
    if arguments.subject_id:
        subject = await studies.subject_summary(connection, str(arguments.subject_id))
        items = await studies.assessments(connection, subject_id=str(arguments.subject_id))
        return {
            "subject": subject.name,
            "grade": _grade(subject.grade),
            "assessments": [_assessment(one) for one in items],
        }
    detail = await studies.course(connection, str(arguments.course_id))
    return {
        "course": _course(detail.course),
        "average_counts": (
            f"{detail.course.average.counted} of {detail.course.average.subjects} subjects"
        ),
        "course_grade": _grade(detail.course.grade) if detail.course.grade else None,
        "subjects": [
            {"subject_id": s.id, "name": s.name, "credits": s.credits, "grade": _grade(s.grade)}
            for s in detail.subjects
        ],
        "assessments": [_assessment(one) for one in detail.assessments],
    }


class FindNotes(BaseModel):
    query: str = Field(min_length=1, max_length=200, description="Palabras, en castellano.")
    limit: int = Field(default=10, ge=1, le=50)


async def find_notes(
    connection: AsyncConnection, arguments: FindNotes, client: httpx.AsyncClient
) -> dict[str, Any]:
    hits = await apuntes.find(connection, client, arguments.query, limit=arguments.limit)
    return {
        "notes": [
            {
                "note_id": hit.id,
                "title": hit.title,
                "course": hit.course,
                "subject": hit.subject,
                "session_start": hit.session_start.astimezone(LOCAL).isoformat()
                if hit.session_start
                else None,
                "fragment": hit.fragment,
            }
            for hit in hits
        ]
    }


class ScheduleSpec(BaseModel):
    rule: Rule = Field(
        description=(
            "Como {freq: 'weekly', by_day: [{weekday: 'TU'}, {weekday: 'TH'}], until: "
            "'2027-01-22'}. until es el último día incluido."
        )
    )
    starts_on: date = Field(description="El primer día del periodo de clases.")
    start_time: time
    end_time: time
    place: str | None = Field(default=None, max_length=200, description="Study o edificio.")
    url: str | None = Field(default=None, max_length=500, description="Enlace a la clase en línea.")


class AssessmentSpec(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: studies.AssessmentKind = "assignment"
    due_on: date | None = None
    due_time: time | None = None
    weight: float | None = Field(
        default=None, gt=0, le=100, description="Tanto por ciento de la nota de su asignatura."
    )
    min_grade: float | None = Field(default=None, ge=0, description="Nota mínima para hacer media.")


class SubjectSpec(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    teacher: str | None = None
    credits: float | None = Field(default=None, gt=0)
    period: str | None = Field(default=None, max_length=60, description='"1.er cuatrimestre".')
    schedule: list[ScheduleSpec] = Field(default_factory=list, max_length=10)
    assessments: list[AssessmentSpec] = Field(default_factory=list, max_length=40)


class CreateCourse(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: studies.Kind = "course"
    institution: str | None = None
    modality: studies.Modality = "in_person"
    starts_on: date | None = None
    ends_on: date | None = None
    status: Literal["planned", "active"] = "active"
    credits: float | None = Field(default=None, gt=0, description="ECTS del total, si los tiene.")
    hours: float | None = Field(default=None, gt=0, description="Horas del curso, si se miden así.")
    scale_max: Literal[10, 100] = 10
    pass_mark: float | None = Field(default=None, gt=0)
    target_grade: float | None = Field(default=None, gt=0)
    tone: int = Field(default=1, ge=1, le=10, description="Color de la paleta, de 1 a 10.")
    campus_url: str | None = None
    tracks: list[studies.Track] | None = Field(
        default=None,
        description="Qué se sigue: grades (notas y media), progress (créditos u horas) y "
        "attendance (asistencia). Lista vacía: nada, solo el horario y los apuntes, como un idioma "
        "sin examen a la vista. Sin decirlo: nada en un idioma, las tres en lo demás.",
    )
    subjects: list[SubjectSpec] = Field(default_factory=list, max_length=60)
    schedule: list[ScheduleSpec] = Field(default_factory=list, max_length=10)
    assessments: list[AssessmentSpec] = Field(default_factory=list, max_length=40)


def _block(spec: ScheduleSpec, subject_id: str | None) -> timetable.ScheduleIn:
    return timetable.ScheduleIn(subject_id=subject_id, **spec.model_dump())


def _item(spec: AssessmentSpec, subject_id: str | None) -> studies.AssessmentIn:
    return studies.AssessmentIn(subject_id=subject_id, **spec.model_dump())


async def create_course(connection: AsyncConnection, arguments: CreateCourse) -> dict[str, Any]:
    fields = arguments.model_dump(exclude={"subjects", "schedule", "assessments"})
    new = studies.CourseIn(
        **fields,
        subjects=[
            studies.SubjectIn(name=s.name, teacher=s.teacher, credits=s.credits, period=s.period)
            for s in arguments.subjects
        ],
    )
    created = await studies.create_course(connection, new, source="tool")
    course_id = created.course.id
    by_position = {s.position: s.id for s in created.subjects}
    sessions = 0
    for position, spec in enumerate(arguments.subjects):
        subject_id = by_position[position]
        for block in spec.schedule:
            sessions += (
                await timetable.add_schedule(connection, course_id, _block(block, subject_id))
            ).sessions
        for item in spec.assessments:
            await studies.add_assessment(
                connection, course_id, _item(item, subject_id), source="tool"
            )
    for block in arguments.schedule:
        sessions += (
            await timetable.add_schedule(connection, course_id, _block(block, None))
        ).sessions
    for item in arguments.assessments:
        await studies.add_assessment(connection, course_id, _item(item, None), source="tool")
    detail = await studies.course(connection, course_id)
    return {
        "course": _course(detail.course),
        "subjects": [{"subject_id": s.id, "name": s.name} for s in detail.subjects],
        "sessions_created": sessions,
        "assessments": len(detail.assessments),
        "open_in_app": f"/study/estudio/{course_id}",
    }


class AddAssessment(AssessmentSpec):
    course_id: UUID = Field(description="El estudio, de get_courses.")
    subject_id: UUID | None = Field(default=None, description="Su asignatura, si la tiene.")


async def add_assessment(connection: AsyncConnection, arguments: AddAssessment) -> dict[str, Any]:
    spec = AssessmentSpec(**arguments.model_dump(exclude={"course_id", "subject_id"}))
    subject_id = str(arguments.subject_id) if arguments.subject_id else None
    added = await studies.add_assessment(
        connection, str(arguments.course_id), _item(spec, subject_id), source="tool"
    )
    return {"assessment": _assessment(added)}


class RecordGrade(BaseModel):
    assessment_id: UUID | None = Field(default=None, description="El evaluable calificado.")
    subject_id: UUID | None = Field(
        default=None, description="O la asignatura, para poner su nota de acta."
    )
    grade: float | None = Field(
        ge=0, description="En la escala del estudio. Null quita la calificación o la de acta."
    )

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.assessment_id is None) == (self.subject_id is None):
            raise ValueError("di el evaluable o la asignatura, uno de los dos")
        return self


async def record_grade(connection: AsyncConnection, arguments: RecordGrade) -> dict[str, Any]:
    if arguments.assessment_id:
        graded = await studies.grade_assessment(
            connection, str(arguments.assessment_id), studies.GradeIn(grade=arguments.grade)
        )
        subject = (
            await studies.subject_summary(connection, graded.subject_id)
            if graded.subject_id
            else None
        )
        return {
            "assessment": _assessment(graded),
            "subject_grade": _grade(subject.grade) if subject else None,
        }
    subject = await studies.record_grade(
        connection, str(arguments.subject_id), studies.RecordIn(final_grade=arguments.grade)
    )
    return {"subject": subject.name, "grade": _grade(subject.grade)}


class AddNote(BaseModel):
    session_id: UUID | None = Field(default=None, description="La clase, de get_week.")
    subject_id: UUID | None = Field(default=None, description="O una asignatura.")
    course_id: UUID | None = Field(default=None, description="O el estudio, sin asignatura.")
    title: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=100000, description="Markdown.")

    @model_validator(mode="after")
    def _somewhere(self) -> Self:
        if not (self.session_id or self.subject_id or self.course_id):
            raise ValueError("di de qué clase, asignatura o estudio son los apuntes")
        return self


async def add_note(
    connection: AsyncConnection, arguments: AddNote, client: httpx.AsyncClient
) -> dict[str, Any]:
    course_id = str(arguments.course_id) if arguments.course_id else None
    if arguments.subject_id and not course_id:
        subject = await studies.subject_summary(connection, str(arguments.subject_id))
        course_id = subject.course_id
    item = notes.NoteIn(
        course_id=course_id or "00000000-0000-0000-0000-000000000000",
        subject_id=str(arguments.subject_id) if arguments.subject_id else None,
        session_id=str(arguments.session_id) if arguments.session_id else None,
        title=arguments.title,
        body=arguments.body,
    )
    added = await apuntes.add_note(connection, client, item, source="tool")
    return {
        "note_id": added.id,
        "course": added.course,
        "subject": added.subject,
        "words": added.words,
    }


class MarkAttendance(BaseModel):
    session_id: UUID = Field(description="La clase, de get_week.")
    attendance: Literal["present", "absent"] | None = Field(
        description="present si fue, absent si no; null lo deja sin marcar."
    )


async def mark_attendance(connection: AsyncConnection, arguments: MarkAttendance) -> dict[str, Any]:
    detail = await timetable.mark_attendance(
        connection,
        str(arguments.session_id),
        timetable.AttendanceIn(attendance=arguments.attendance),
    )
    return {"session": _session(detail.session)}


def _schedule(one: timetable.ScheduleOut) -> dict[str, Any]:
    return {
        "schedule_id": one.id,
        "subject_id": one.subject_id,
        "subject": one.subject,
        "repeats": one.phrase,
        "rule": one.rule.model_dump(mode="json", exclude_none=True),
        "starts_on": one.starts_on.isoformat(),
        "start_time": one.start_time.isoformat(timespec="minutes"),
        "end_time": one.end_time.isoformat(timespec="minutes"),
        "place": one.place,
        "url": one.url,
        "sessions": one.sessions,
    }


def _material(one: notes.MaterialOut) -> dict[str, Any]:
    return {
        "material_id": one.id,
        "subject": one.subject,
        "title": one.title,
        "url": one.url,
        "file": one.filename,
    }


def _note(one: notes.NoteBrief) -> dict[str, Any]:
    return {
        "note_id": one.id,
        "title": one.title,
        "subject": one.subject,
        "session_start": one.session_start.astimezone(LOCAL).isoformat()
        if one.session_start
        else None,
        "excerpt": one.excerpt,
        "words": one.words,
    }


class GetCourse(BaseModel):
    course_id: UUID = Field(description="El estudio, de get_courses.")


async def get_course(
    connection: AsyncConnection, arguments: GetCourse, client: httpx.AsyncClient
) -> dict[str, Any]:
    course_id = str(arguments.course_id)
    detail = await studies.course(connection, course_id)
    try:
        found: list[dict[str, Any]] | None = [
            _note(one) for one in await apuntes.notes(connection, client, course_id=course_id)
        ]
        unavailable = None
    except apuntes.Unavailable as error:
        found, unavailable = None, str(error)
    return {
        "course": _course(detail.course),
        "subjects": [
            {
                "subject_id": s.id,
                "name": s.name,
                "teacher": s.teacher,
                "credits": s.credits,
                "period": s.period,
                "position": s.position,
                "final_grade": s.final_grade,
                "verdict": s.grade.verdict,
            }
            for s in detail.subjects
        ],
        "schedules": [_schedule(b) for b in await timetable.schedules(connection, course_id)],
        "assessments": [_assessment(one) for one in detail.assessments],
        "materials": [
            _material(one) for one in await notes.materials(connection, course_id=course_id)
        ],
        "notes": found,
        **({"notes_unavailable": unavailable} if unavailable else {}),
        "open_in_app": f"/study/estudio/{course_id}",
    }


class GetNote(BaseModel):
    note_id: UUID = Field(description="Los apuntes, de find_notes o get_course.")


async def get_note(
    connection: AsyncConnection, arguments: GetNote, client: httpx.AsyncClient
) -> dict[str, Any]:
    found = await apuntes.note(connection, client, str(arguments.note_id))
    return {
        **_note(found),
        "course": found.course,
        "session_id": found.session_id,
        "body": found.body,
    }


def _build[T: BaseModel](model: type[T], **fields: Any) -> T:
    try:
        return model(**fields)
    except ValidationError as error:
        reasons = [e["msg"].removeprefix("Value error, ") for e in error.errors()]
        raise studies.Conflict("; ".join(reasons)) from error


def _same(stored: str, given: str) -> bool:
    return stored.strip().casefold() == given.strip().casefold()


def _mismatch(what: str, stored: str, given: str) -> dict[str, Any]:
    return {
        "deleted": None,
        "note": f"{what} se llama «{stored}», no «{given}»; no he borrado nada",
    }


def _changes(arguments: BaseModel, *ids: str) -> dict[str, Any]:
    return {k: getattr(arguments, k) for k in arguments.model_fields_set if k not in ids}


COURSE_FIELDS = (
    "name",
    "kind",
    "institution",
    "modality",
    "starts_on",
    "ends_on",
    "status",
    "credits",
    "hours",
    "scale_max",
    "pass_mark",
    "target_grade",
    "tone",
    "campus_url",
    "note",
    "tracks",
)
COURSE_REQUIRED = {
    "name",
    "kind",
    "modality",
    "status",
    "scale_max",
    "pass_mark",
    "tone",
    "tracks",
}


class UpdateCourse(BaseModel):
    course_id: UUID = Field(description="El estudio, de get_courses.")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: studies.Kind | None = None
    institution: str | None = Field(default=None, description="Null la quita.")
    modality: studies.Modality | None = None
    starts_on: date | None = Field(default=None, description="Null la quita.")
    ends_on: date | None = Field(default=None, description="Null la quita.")
    status: Literal["planned", "active"] | None = Field(
        default=None,
        description="Planeado o en curso. Para terminarlo o abandonarlo, archive_course.",
    )
    credits: float | None = Field(default=None, gt=0, description="Null los quita.")
    hours: float | None = Field(default=None, gt=0, description="Null las quita.")
    scale_max: Literal[10, 100] | None = Field(
        default=None, description="Si cambia y no se dice el aprobado, pasa a la mitad."
    )
    pass_mark: float | None = Field(default=None, gt=0)
    target_grade: float | None = Field(default=None, gt=0, description="Null lo quita.")
    tone: int | None = Field(default=None, ge=1, le=10)
    campus_url: str | None = Field(default=None, description="Null lo quita.")
    note: str | None = Field(default=None, max_length=4000, description="Null la quita.")
    tracks: list[studies.Track] | None = Field(
        default=None,
        description="Qué se sigue: grades, progress, attendance. Lista vacía: nada. Sin decirlo, "
        "se queda como estaba.",
    )


async def update_course(connection: AsyncConnection, arguments: UpdateCourse) -> dict[str, Any]:
    course_id = str(arguments.course_id)
    current = (await studies.course(connection, course_id)).course
    fields = {k: getattr(current, k) for k in COURSE_FIELDS}
    if fields["status"] not in ("planned", "active"):
        fields["status"] = "active"
    changes = _changes(arguments, "course_id")
    for name, value in changes.items():
        if value is None and name in COURSE_REQUIRED:
            continue
        fields[name] = value
    if "scale_max" in changes and "pass_mark" not in changes:
        fields["pass_mark"] = None
    edit = _build(studies.CourseEdit, **fields, tz=current.tz, final_grade=current.final_grade)
    detail = await studies.update_course(connection, course_id, edit)
    return {"course": _course(detail.course)}


class ArchiveCourse(BaseModel):
    course_id: UUID = Field(description="El estudio, de get_courses.")
    outcome: Literal["finished", "abandoned"] = Field(
        description="finished si se terminó, abandoned si se dejó."
    )
    closed_on: date | None = Field(default=None, description="Cuándo; hoy si no se dice.")
    final_grade: float | None = Field(
        default=None, ge=0, description="La nota final del estudio, en su escala, si la tiene."
    )


async def archive_course(connection: AsyncConnection, arguments: ArchiveCourse) -> dict[str, Any]:
    detail = await studies.close_course(
        connection,
        str(arguments.course_id),
        studies.CloseIn(
            status=arguments.outcome,
            closed_on=arguments.closed_on,
            final_grade=arguments.final_grade,
        ),
    )
    return {"course": _course(detail.course)}


class ReopenCourse(BaseModel):
    course_id: UUID = Field(description="El estudio archivado, de get_courses con scope archive.")


async def reopen_course(connection: AsyncConnection, arguments: ReopenCourse) -> dict[str, Any]:
    detail = await studies.reopen_course(connection, str(arguments.course_id))
    return {"course": _course(detail.course)}


class DeleteCourse(BaseModel):
    course_id: UUID = Field(description="El estudio, de get_courses.")
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Su nombre tal como está guardado. Si no coincide no se borra nada.",
    )


async def delete_course(connection: AsyncConnection, arguments: DeleteCourse) -> dict[str, Any]:
    course_id = str(arguments.course_id)
    detail = await studies.course(connection, course_id)
    if not _same(detail.course.name, arguments.name):
        return _mismatch("ese estudio", detail.course.name, arguments.name)
    await studies.delete_course(connection, course_id)
    return {
        "deleted": {
            "course_id": course_id,
            "name": detail.course.name,
            "subjects": len(detail.subjects),
            "assessments": len(detail.assessments),
        },
        "note": "los apuntes siguen en Notas, en su carpeta",
    }


class AddSubject(SubjectSpec):
    course_id: UUID = Field(description="El estudio, de get_courses.")


async def add_subject(connection: AsyncConnection, arguments: AddSubject) -> dict[str, Any]:
    course_id = str(arguments.course_id)
    added = await studies.add_subject(
        connection,
        course_id,
        studies.SubjectIn(
            name=arguments.name,
            teacher=arguments.teacher,
            credits=arguments.credits,
            period=arguments.period,
        ),
    )
    sessions = 0
    for block in arguments.schedule:
        sessions += (
            await timetable.add_schedule(connection, course_id, _block(block, added.id))
        ).sessions
    for item in arguments.assessments:
        await studies.add_assessment(connection, course_id, _item(item, added.id), source="tool")
    return {
        "subject_id": added.id,
        "name": added.name,
        "sessions_created": sessions,
        "assessments": len(arguments.assessments),
    }


class UpdateSubject(BaseModel):
    subject_id: UUID = Field(description="La asignatura, de get_course.")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    teacher: str | None = Field(default=None, max_length=200, description="Null lo quita.")
    credits: float | None = Field(default=None, gt=0, description="Null los quita.")
    period: str | None = Field(default=None, max_length=60, description="Null lo quita.")
    position: int | None = Field(
        default=None, ge=0, le=100, description="Su sitio en la lista del estudio, desde 0."
    )


async def update_subject(connection: AsyncConnection, arguments: UpdateSubject) -> dict[str, Any]:
    subject_id = str(arguments.subject_id)
    current = await studies.subject_summary(connection, subject_id)
    changes = _changes(arguments, "subject_id", "position")
    fields = {k: getattr(current, k) for k in ("name", "teacher", "credits", "period")}
    fields.update({k: v for k, v in changes.items() if not (k == "name" and v is None)})
    if changes:
        await studies.update_subject(connection, subject_id, _build(studies.SubjectIn, **fields))
    if arguments.position is not None:
        await studies.move_subject(connection, subject_id, arguments.position)
    subject = await studies.subject_summary(connection, subject_id)
    return {
        "subject_id": subject.id,
        "name": subject.name,
        "teacher": subject.teacher,
        "credits": subject.credits,
        "period": subject.period,
        "position": subject.position,
    }


class DeleteSubject(BaseModel):
    subject_id: UUID = Field(description="La asignatura, de get_course.")
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Su nombre tal como está guardado. Si no coincide no se borra nada.",
    )


async def delete_subject(connection: AsyncConnection, arguments: DeleteSubject) -> dict[str, Any]:
    subject_id = str(arguments.subject_id)
    current = await studies.subject_summary(connection, subject_id)
    if not _same(current.name, arguments.name):
        return _mismatch("esa asignatura", current.name, arguments.name)
    await studies.delete_subject(connection, subject_id)
    return {
        "deleted": {"subject_id": subject_id, "name": current.name},
        "note": "los apuntes siguen en Notas, en su carpeta",
    }


class AddSchedule(ScheduleSpec):
    course_id: UUID = Field(description="El estudio, de get_courses.")
    subject_id: UUID | None = Field(default=None, description="Su asignatura, si la tiene.")


async def add_schedule(connection: AsyncConnection, arguments: AddSchedule) -> dict[str, Any]:
    spec = ScheduleSpec(**arguments.model_dump(exclude={"course_id", "subject_id"}))
    subject_id = str(arguments.subject_id) if arguments.subject_id else None
    block = _build(timetable.ScheduleIn, subject_id=subject_id, **spec.model_dump())
    added = await timetable.add_schedule(connection, str(arguments.course_id), block)
    return {"schedule": _schedule(added)}


class UpdateSchedule(BaseModel):
    schedule_id: UUID = Field(description="El bloque del horario, de get_course.")
    rule: Rule | None = Field(default=None, description="La regla entera, como en create_course.")
    starts_on: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    place: str | None = Field(default=None, max_length=200, description="Null lo quita.")
    url: str | None = Field(default=None, max_length=500, description="Null lo quita.")
    subject_id: UUID | None = Field(
        default=None, description="Otra asignatura del mismo estudio; null lo deja sin asignatura."
    )


async def update_schedule(connection: AsyncConnection, arguments: UpdateSchedule) -> dict[str, Any]:
    schedule_id = str(arguments.schedule_id)
    current = await timetable.schedule(connection, schedule_id)
    fields: dict[str, Any] = {
        "subject_id": current.subject_id,
        "rule": current.rule,
        "starts_on": current.starts_on,
        "start_time": current.start_time,
        "end_time": current.end_time,
        "place": current.place,
        "url": current.url,
    }
    for name, value in _changes(arguments, "schedule_id").items():
        if value is None and name in ("rule", "starts_on", "start_time", "end_time"):
            continue
        fields[name] = str(value) if isinstance(value, UUID) else value
    updated = await timetable.update_schedule(
        connection, schedule_id, _build(timetable.ScheduleIn, **fields)
    )
    return {
        "schedule": _schedule(updated),
        "note": "las clases que ya pasaron o que tocaste (movidas, con apuntes) no cambian",
    }


class DeleteSchedule(BaseModel):
    schedule_id: UUID = Field(description="El bloque del horario, de get_course.")


async def delete_schedule(connection: AsyncConnection, arguments: DeleteSchedule) -> dict[str, Any]:
    removed = await timetable.delete_schedule(connection, str(arguments.schedule_id))
    return {
        "deleted": {"schedule_id": str(arguments.schedule_id), "removed_sessions": removed},
        "note": "las clases que ya pasaron o que tocaste se quedan, sueltas",
    }


def _local(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=LOCAL)


class AddSession(BaseModel):
    course_id: UUID = Field(description="El estudio, de get_courses.")
    subject_id: UUID | None = Field(default=None, description="Su asignatura, si la tiene.")
    kind: Literal["class", "tutorial", "event"] = Field(
        default="event", description="class: una clase de más; tutorial; event: jornada, defensa."
    )
    title: str | None = Field(
        default=None, max_length=200, description="Hace falta salvo en una clase."
    )
    starts_at: datetime = Field(description="Sin zona, hora de Madrid.")
    ends_at: datetime = Field(description="Sin zona, hora de Madrid.")
    place: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)


async def add_session(connection: AsyncConnection, arguments: AddSession) -> dict[str, Any]:
    item = _build(
        timetable.SessionIn,
        kind=arguments.kind,
        title=arguments.title,
        subject_id=str(arguments.subject_id) if arguments.subject_id else None,
        starts_at=_local(arguments.starts_at),
        ends_at=_local(arguments.ends_at),
        place=arguments.place,
        url=arguments.url,
    )
    added = await timetable.add_session(connection, str(arguments.course_id), item)
    return {"session": _session(added.session)}


class UpdateSession(BaseModel):
    session_id: UUID = Field(description="La clase, de get_week.")
    starts_at: datetime | None = Field(
        default=None, description="Sin zona, hora de Madrid. Si no se dice el fin, dura lo mismo."
    )
    ends_at: datetime | None = None
    place: str | None = Field(default=None, max_length=200, description="Null lo quita.")
    url: str | None = Field(default=None, max_length=500, description="Null lo quita.")
    title: str | None = Field(
        default=None, max_length=200, description="Solo en una sesión suelta; una clase no lo usa."
    )
    status: Literal["scheduled", "cancelled"] | None = Field(
        default=None, description="cancelled la cancela; scheduled la recupera."
    )
    topic: str | None = Field(
        default=None, max_length=300, description="De qué fue o de qué va. Null lo quita."
    )


async def update_session(connection: AsyncConnection, arguments: UpdateSession) -> dict[str, Any]:
    session_id = str(arguments.session_id)
    current = (await timetable.session(connection, session_id)).session
    changes = _changes(arguments, "session_id", "topic")
    if changes:
        starts = _local(arguments.starts_at) if arguments.starts_at else current.starts_at
        if arguments.ends_at:
            ends = _local(arguments.ends_at)
        else:
            ends = starts + (current.ends_at - current.starts_at)
        fields = {
            "starts_at": starts,
            "ends_at": ends,
            "place": current.place,
            "url": current.url,
            "status": current.status,
            "title": current.title,
        }
        for name in ("place", "url", "title", "status"):
            if name in changes and not (name in ("status", "title") and changes[name] is None):
                fields[name] = changes[name]
        await timetable.update_session(
            connection, session_id, _build(timetable.SessionEdit, **fields)
        )
    if "topic" in arguments.model_fields_set:
        await timetable.set_topic(connection, session_id, timetable.TopicIn(topic=arguments.topic))
    detail = await timetable.session(connection, session_id)
    return {"session": _session(detail.session)}


class DeleteSession(BaseModel):
    session_id: UUID = Field(description="La sesión suelta, de get_week.")


async def delete_session(connection: AsyncConnection, arguments: DeleteSession) -> dict[str, Any]:
    await timetable.delete_session(connection, str(arguments.session_id))
    return {"deleted": {"session_id": str(arguments.session_id)}}


class UpdateAssessment(BaseModel):
    assessment_id: UUID = Field(description="El evaluable, de get_grades o get_week.")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    kind: studies.AssessmentKind | None = None
    subject_id: UUID | None = Field(
        default=None, description="Otra asignatura del mismo estudio; null lo cuelga del estudio."
    )
    due_on: date | None = Field(default=None, description="Null quita la fecha.")
    due_time: time | None = Field(default=None, description="Null quita la hora.")
    weight: float | None = Field(default=None, gt=0, le=100, description="Null quita el peso.")
    min_grade: float | None = Field(default=None, ge=0, description="Null quita la mínima.")
    status: Literal["pending", "submitted"] | None = Field(
        default=None,
        description="Pendiente o entregado. La nota se pone con record_grade y manda sobre esto.",
    )
    note: str | None = Field(default=None, max_length=2000, description="Null la quita.")


async def update_assessment(
    connection: AsyncConnection, arguments: UpdateAssessment
) -> dict[str, Any]:
    assessment_id = str(arguments.assessment_id)
    current = await studies.assessment(connection, assessment_id)
    fields: dict[str, Any] = {
        k: getattr(current, k)
        for k in (
            "title",
            "kind",
            "subject_id",
            "due_on",
            "due_time",
            "weight",
            "min_grade",
            "status",
            "grade",
            "note",
        )
    }
    for name, value in _changes(arguments, "assessment_id").items():
        if value is None and name in ("title", "kind", "status"):
            continue
        fields[name] = str(value) if isinstance(value, UUID) else value
    if "due_on" in arguments.model_fields_set and arguments.due_on is None:
        fields["due_time"] = None
    updated = await studies.update_assessment(
        connection, assessment_id, _build(studies.AssessmentIn, **fields)
    )
    return {"assessment": _assessment(updated)}


class DeleteAssessment(BaseModel):
    assessment_id: UUID = Field(description="El evaluable, de get_grades o get_week.")
    title: str = Field(
        min_length=1,
        max_length=200,
        description="Su título tal como está guardado. Si no coincide no se borra nada.",
    )


async def delete_assessment(
    connection: AsyncConnection, arguments: DeleteAssessment
) -> dict[str, Any]:
    assessment_id = str(arguments.assessment_id)
    current = await studies.assessment(connection, assessment_id)
    if not _same(current.title, arguments.title):
        return _mismatch("ese evaluable", current.title, arguments.title)
    await studies.delete_assessment(connection, assessment_id)
    return {"deleted": {"assessment_id": assessment_id, "title": current.title}}


class UpdateNote(BaseModel):
    note_id: UUID = Field(description="Los apuntes, de find_notes o get_course.")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(
        default=None, min_length=1, max_length=100000, description="Markdown; sustituye el texto."
    )
    append: str | None = Field(
        default=None,
        min_length=1,
        max_length=100000,
        description="Markdown que se añade al final, sin reescribir lo que hay.",
    )
    subject_id: UUID | None = Field(
        default=None, description="Los pasa a otra asignatura del mismo estudio."
    )

    @model_validator(mode="after")
    def _one_text(self) -> Self:
        if self.body is not None and self.append is not None:
            raise ValueError("o body o append, no los dos")
        return self


async def update_note(
    connection: AsyncConnection, arguments: UpdateNote, client: httpx.AsyncClient
) -> dict[str, Any]:
    note_id = str(arguments.note_id)
    current = await apuntes.note(connection, client, note_id)
    body = arguments.body if arguments.body is not None else current.body
    if arguments.append:
        body = f"{current.body.rstrip()}\n\n{arguments.append}".lstrip()
    edit = _build(
        notes.NoteEdit,
        title=arguments.title or current.title,
        body=body,
        subject_id=str(arguments.subject_id) if arguments.subject_id else None,
    )
    updated = await apuntes.update_note(connection, client, note_id, edit)
    return {**_note(updated), "course": updated.course}


class DeleteNote(BaseModel):
    note_id: UUID = Field(description="Los apuntes, de find_notes o get_course.")


async def delete_note(
    connection: AsyncConnection, arguments: DeleteNote, client: httpx.AsyncClient
) -> dict[str, Any]:
    note_id = str(arguments.note_id)
    current = await apuntes.note(connection, client, note_id)
    await apuntes.delete_note(connection, client, note_id)
    return {
        "deleted": {"note_id": note_id, "title": current.title},
        "note": "están en la papelera de Notas, de donde se recuperan",
    }


class AddMaterial(BaseModel):
    course_id: UUID = Field(description="El estudio, de get_courses.")
    subject_id: UUID | None = Field(default=None, description="Su asignatura, si la tiene.")
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=1000, description="El enlace al material.")


async def add_material(connection: AsyncConnection, arguments: AddMaterial) -> dict[str, Any]:
    item = _build(
        notes.MaterialIn,
        title=arguments.title,
        url=arguments.url,
        subject_id=str(arguments.subject_id) if arguments.subject_id else None,
    )
    added = await notes.add_material(connection, str(arguments.course_id), item)
    return {"material": _material(added)}


class DeleteMaterial(BaseModel):
    material_id: UUID = Field(description="El material, de get_course.")


async def delete_material(connection: AsyncConnection, arguments: DeleteMaterial) -> dict[str, Any]:
    await notes.delete_material(connection, str(arguments.material_id))
    return {"deleted": {"material_id": str(arguments.material_id)}}


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]
    asks_notes: bool = False

    @property
    def asks_the_hub(self) -> bool:
        return self.asks_notes


TOOLS: dict[str, Tool] = {
    "get_courses": Tool(GetCourses, get_courses),
    "get_week": Tool(GetWeek, get_week),
    "get_grades": Tool(GetGrades, get_grades),
    "find_notes": Tool(FindNotes, find_notes, asks_notes=True),
    "create_course": Tool(CreateCourse, create_course),
    "add_assessment": Tool(AddAssessment, add_assessment),
    "record_grade": Tool(RecordGrade, record_grade),
    "add_note": Tool(AddNote, add_note, asks_notes=True),
    "mark_attendance": Tool(MarkAttendance, mark_attendance),
    "get_course": Tool(GetCourse, get_course, asks_notes=True),
    "get_note": Tool(GetNote, get_note, asks_notes=True),
    "update_course": Tool(UpdateCourse, update_course),
    "archive_course": Tool(ArchiveCourse, archive_course),
    "reopen_course": Tool(ReopenCourse, reopen_course),
    "delete_course": Tool(DeleteCourse, delete_course),
    "add_subject": Tool(AddSubject, add_subject),
    "update_subject": Tool(UpdateSubject, update_subject),
    "delete_subject": Tool(DeleteSubject, delete_subject),
    "add_schedule": Tool(AddSchedule, add_schedule),
    "update_schedule": Tool(UpdateSchedule, update_schedule),
    "delete_schedule": Tool(DeleteSchedule, delete_schedule),
    "add_session": Tool(AddSession, add_session),
    "update_session": Tool(UpdateSession, update_session),
    "delete_session": Tool(DeleteSession, delete_session),
    "update_assessment": Tool(UpdateAssessment, update_assessment),
    "delete_assessment": Tool(DeleteAssessment, delete_assessment),
    "update_note": Tool(UpdateNote, update_note, asks_notes=True),
    "delete_note": Tool(DeleteNote, delete_note, asks_notes=True),
    "add_material": Tool(AddMaterial, add_material),
    "delete_material": Tool(DeleteMaterial, delete_material),
}
