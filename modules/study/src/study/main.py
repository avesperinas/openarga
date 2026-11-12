from __future__ import annotations

import hmac
import os
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import text

import arga_contracts as contracts
from arga_module.service import Service
from arga_tenancy import require_person
from study import apuntes, moving, notes, publisher, studies, timetable, tools, widgets
from study import panel as home_panel

MODULE_ID = "study"

service = Service(
    MODULE_ID,
    "Study",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    errors={studies.NotFound: 404, studies.Conflict: 409, apuntes.Unavailable: 503},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
as_app = service.as_app


def notes_client() -> httpx.AsyncClient:
    if getattr(app.state, "client", None) is None:
        raise apuntes.Unavailable("el cliente del kernel no está listo")
    return service.client()


async def _run(action, *args, **kwargs):
    async with as_app() as connection:
        return await action(connection, *args, **kwargs)


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Study no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Study")
    if capability != contracts.AGENDA_MOVE:
        raise HTTPException(status_code=404, detail=f"Study no sabe hacer '{capability}'")
    require_person()
    try:
        asked = contracts.AgendaMove.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    answer = await _run(moving.move, asked)
    print(f"calendario {asked.uid} movido por {x_arga_module}", flush=True)
    return answer


@app.get("/home")
async def read_home(week: date | None = None) -> studies.Home:
    return await _run(studies.home, week)


@app.get("/courses")
async def list_courses(
    scope: Literal["current", "archive", "all"] = "current",
) -> list[studies.CourseOut]:
    return await _run(studies.courses, scope)


@app.post("/courses", status_code=201)
async def create_course(request: studies.CourseIn) -> studies.CourseDetail:
    return await _run(studies.create_course, request)


@app.get("/courses/{course_id}")
async def read_course(course_id: UUID) -> studies.CourseDetail:
    return await _run(studies.course, str(course_id))


@app.put("/courses/{course_id}")
async def update_course(course_id: UUID, request: studies.CourseEdit) -> studies.CourseDetail:
    return await _run(studies.update_course, str(course_id), request)


@app.post("/courses/{course_id}/close")
async def close_course(course_id: UUID, request: studies.CloseIn) -> studies.CourseDetail:
    return await _run(studies.close_course, str(course_id), request)


@app.post("/courses/{course_id}/reopen")
async def reopen_course(course_id: UUID) -> studies.CourseDetail:
    return await _run(studies.reopen_course, str(course_id))


@app.delete("/courses/{course_id}", status_code=204)
async def delete_course(course_id: UUID) -> Response:
    await _run(studies.delete_course, str(course_id))
    return Response(status_code=204)


@app.get("/courses/{course_id}/certificate")
async def read_certificate(course_id: UUID) -> Response:
    async def find(connection):
        await studies._own(connection, "study_course", str(course_id))
        found = await connection.scalar(
            text("select certificate_id from study.study_course where id = :id"),
            {"id": str(course_id)},
        )
        if found is None:
            raise studies.NotFound("el estudio no tiene certificado")
        return await notes.read_file(connection, str(found))

    name, kind, content, inline = await _run(find)
    return Response(
        content,
        media_type=kind,
        headers={
            "content-disposition": f"{'inline' if inline else 'attachment'}; "
            f"filename*=UTF-8''{quote(name)}",
            "cache-control": "private, no-cache",
            "x-content-type-options": "nosniff",
        },
    )


@app.put("/courses/{course_id}/certificate", status_code=201)
async def upload_certificate(
    course_id: UUID, request: Request, filename: str = "certificado"
) -> notes.AttachmentOut:
    content = await _body(request)

    async def save(connection):
        await studies._own(connection, "study_course", str(course_id))
        saved = await notes.save_file(
            connection, filename, content, request.headers.get("content-type", "")
        )
        await notes.set_certificate(connection, str(course_id), saved.id)
        return saved

    return await _run(save)


@app.post("/courses/{course_id}/subjects", status_code=201)
async def add_subject(course_id: UUID, request: studies.SubjectIn) -> studies.SubjectOut:
    return await _run(studies.add_subject, str(course_id), request)


class SubjectDetail(studies.BaseModel):
    subject: studies.SubjectOut
    course: studies.CourseOut
    assessments: list[studies.AssessmentOut]
    sessions: list[studies.SessionBrief]
    notes: list[notes.NoteBrief]
    notes_unavailable: str | None = None
    materials: list[notes.MaterialOut]
    schedules: list[timetable.ScheduleOut]


@app.get("/subjects/{subject_id}")
async def read_subject(subject_id: UUID) -> SubjectDetail:

    async def read(connection):
        subject = await studies.subject_summary(connection, str(subject_id))
        course = await studies.course(connection, subject.course_id)
        try:
            found = await apuntes.notes(connection, notes_client(), subject_id=str(subject_id))
            unavailable = None
        except apuntes.Unavailable as error:
            found, unavailable = [], str(error)
        return SubjectDetail(
            subject=subject,
            course=course.course,
            assessments=await studies.assessments(connection, subject_id=str(subject_id)),
            sessions=await timetable.course_sessions(connection, subject_id=str(subject_id)),
            notes=found,
            notes_unavailable=unavailable,
            materials=await notes.materials(connection, subject_id=str(subject_id)),
            schedules=[
                s
                for s in await timetable.schedules(connection, subject.course_id)
                if s.subject_id == str(subject_id)
            ],
        )

    return await _run(read)


@app.put("/subjects/{subject_id}")
async def update_subject(subject_id: UUID, request: studies.SubjectIn) -> studies.SubjectOut:
    return await _run(studies.update_subject, str(subject_id), request)


@app.put("/subjects/{subject_id}/record")
async def record_grade(subject_id: UUID, request: studies.RecordIn) -> studies.SubjectOut:
    return await _run(studies.record_grade, str(subject_id), request)


@app.put("/subjects/{subject_id}/position", status_code=204)
async def move_subject(subject_id: UUID, position: int = Query(ge=0, le=100)) -> Response:
    await _run(studies.move_subject, str(subject_id), position)
    return Response(status_code=204)


@app.delete("/subjects/{subject_id}", status_code=204)
async def delete_subject(subject_id: UUID) -> Response:
    await _run(studies.delete_subject, str(subject_id))
    return Response(status_code=204)


@app.get("/courses/{course_id}/schedules")
async def list_schedules(course_id: UUID) -> list[timetable.ScheduleOut]:
    return await _run(timetable.schedules, str(course_id))


@app.post("/courses/{course_id}/schedules", status_code=201)
async def add_schedule(course_id: UUID, request: timetable.ScheduleIn) -> timetable.ScheduleOut:
    return await _run(timetable.add_schedule, str(course_id), request)


@app.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: UUID, request: timetable.ScheduleIn
) -> timetable.ScheduleOut:
    return await _run(timetable.update_schedule, str(schedule_id), request)


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: UUID) -> dict:
    removed = await _run(timetable.delete_schedule, str(schedule_id))
    return {"removed_sessions": removed}


@app.get("/sessions")
async def list_sessions(
    since: Annotated[datetime, Query(alias="from")],
    until: Annotated[datetime, Query(alias="to")],
    course_id: UUID | None = None,
) -> list[studies.SessionBrief]:
    if since.tzinfo is None or until.tzinfo is None:
        raise HTTPException(status_code=422, detail="las horas van con su zona")
    return await _run(
        timetable.sessions, since, until, course_id=str(course_id) if course_id else None
    )


@app.get("/courses/{course_id}/sessions")
async def list_course_sessions(course_id: UUID) -> list[studies.SessionBrief]:
    async def read(connection):
        await studies._own(connection, "study_course", str(course_id))
        return await timetable.course_sessions(connection, course_id=str(course_id))

    return await _run(read)


@app.post("/courses/{course_id}/sessions", status_code=201)
async def add_session(course_id: UUID, request: timetable.SessionIn) -> timetable.SessionDetail:
    return await _run(timetable.add_session, str(course_id), request)


class SessionPage(studies.BaseModel):
    detail: timetable.SessionDetail
    notes: list[notes.Note]
    notes_unavailable: str | None = None
    files: list[notes.AttachmentOut]


@app.get("/sessions/{session_id}")
async def read_session(session_id: UUID) -> SessionPage:

    async def read(connection):
        detail = await timetable.session(connection, str(session_id))
        client = notes_client()
        try:
            briefs = await apuntes.notes(connection, client, session_id=str(session_id))
            found = [await apuntes.note(connection, client, brief.id) for brief in briefs]
            unavailable = None
        except apuntes.Unavailable as error:
            found, unavailable = [], str(error)
        return SessionPage(
            detail=detail,
            notes=found,
            notes_unavailable=unavailable,
            files=await notes.session_files(connection, str(session_id)),
        )

    return await _run(read)


@app.put("/sessions/{session_id}")
async def update_session(
    session_id: UUID, request: timetable.SessionEdit
) -> timetable.SessionDetail:
    return await _run(timetable.update_session, str(session_id), request)


@app.put("/sessions/{session_id}/attendance")
async def mark_attendance(
    session_id: UUID, request: timetable.AttendanceIn
) -> timetable.SessionDetail:
    return await _run(timetable.mark_attendance, str(session_id), request)


@app.put("/sessions/{session_id}/topic")
async def set_topic(session_id: UUID, request: timetable.TopicIn) -> timetable.SessionDetail:
    return await _run(timetable.set_topic, str(session_id), request)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: UUID) -> Response:
    await _run(timetable.delete_session, str(session_id))
    return Response(status_code=204)


@app.get("/assessments")
async def list_assessments(
    pending: bool = False,
    since: Annotated[date | None, Query(alias="from")] = None,
    until: Annotated[date | None, Query(alias="to")] = None,
) -> list[studies.AssessmentOut]:
    return await _run(studies.assessments, pending_only=pending, since=since, until=until)


@app.post("/courses/{course_id}/assessments", status_code=201)
async def add_assessment(course_id: UUID, request: studies.AssessmentIn) -> studies.AssessmentOut:
    return await _run(studies.add_assessment, str(course_id), request)


@app.get("/assessments/{assessment_id}")
async def read_assessment(assessment_id: UUID) -> studies.AssessmentOut:
    return await _run(studies.assessment, str(assessment_id))


@app.put("/assessments/{assessment_id}")
async def update_assessment(
    assessment_id: UUID, request: studies.AssessmentIn
) -> studies.AssessmentOut:
    return await _run(studies.update_assessment, str(assessment_id), request)


@app.put("/assessments/{assessment_id}/grade")
async def grade_assessment(assessment_id: UUID, request: studies.GradeIn) -> studies.AssessmentOut:
    return await _run(studies.grade_assessment, str(assessment_id), request)


@app.delete("/assessments/{assessment_id}", status_code=204)
async def delete_assessment(assessment_id: UUID) -> Response:
    await _run(studies.delete_assessment, str(assessment_id))
    return Response(status_code=204)


@app.get("/notes")
async def list_notes(
    q: str | None = Query(default=None, max_length=200),
    course_id: UUID | None = None,
    subject_id: UUID | None = None,
) -> list[notes.NoteBrief] | list[notes.Hit]:
    if q and q.strip():
        return await _run(apuntes.find, notes_client(), q)
    return await _run(
        apuntes.notes,
        notes_client(),
        course_id=str(course_id) if course_id else None,
        subject_id=str(subject_id) if subject_id else None,
    )


@app.post("/notes", status_code=201)
async def add_note(request: notes.NoteIn) -> notes.Note:
    return await _run(apuntes.add_note, notes_client(), request)


@app.get("/notes/{note_id}")
async def read_note(note_id: UUID) -> notes.Note:
    return await _run(apuntes.note, notes_client(), str(note_id))


@app.put("/notes/{note_id}")
async def update_note(note_id: UUID, request: notes.NoteEdit) -> notes.Note:
    return await _run(apuntes.update_note, notes_client(), str(note_id), request)


@app.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: UUID) -> Response:
    await _run(apuntes.delete_note, notes_client(), str(note_id))
    return Response(status_code=204)


async def _body(request: Request) -> bytes:
    declared = int(request.headers.get("content-length") or 0)
    if declared > notes.FILE_LIMIT:
        raise HTTPException(status_code=413, detail="el fichero pasa de 20 MB")
    content = await request.body()
    if len(content) > notes.FILE_LIMIT:
        raise HTTPException(status_code=413, detail="el fichero pasa de 20 MB")
    return content


@app.post("/attachments", status_code=201)
async def upload_file(
    request: Request,
    filename: str = Query(default="fichero", max_length=200),
    note_id: UUID | None = None,
    session_id: UUID | None = None,
) -> notes.AttachmentOut:
    content = await _body(request)

    async def save(connection):
        saved = await notes.save_file(
            connection, filename, content, request.headers.get("content-type", "")
        )
        if note_id or session_id:
            place = notes.Place(
                note_id=str(note_id) if note_id else None,
                session_id=str(session_id) if session_id else None,
            )
            return await notes.attach(connection, saved.id, place)
        return saved

    return await _run(save)


@app.get("/attachments/{attachment_id}")
async def read_file(attachment_id: UUID, download: bool = False) -> Response:
    name, kind, content, inline = await _run(notes.read_file, str(attachment_id))
    disposition = "inline" if inline and not download else "attachment"
    return Response(
        content,
        media_type=kind,
        headers={
            "content-disposition": f"{disposition}; filename*=UTF-8''{quote(name)}",
            "cache-control": "private, max-age=31536000, immutable",
            "x-content-type-options": "nosniff",
        },
    )


@app.delete("/attachments/{attachment_id}", status_code=204)
async def delete_file(attachment_id: UUID) -> Response:
    await _run(notes.delete_file, str(attachment_id))
    return Response(status_code=204)


@app.get("/courses/{course_id}/materials")
async def list_materials(course_id: UUID) -> list[notes.MaterialOut]:
    async def read(connection):
        await studies._own(connection, "study_course", str(course_id))
        return await notes.materials(connection, course_id=str(course_id))

    return await _run(read)


@app.post("/courses/{course_id}/materials", status_code=201)
async def add_material(course_id: UUID, request: notes.MaterialIn) -> notes.MaterialOut:
    return await _run(notes.add_material, str(course_id), request)


@app.post("/courses/{course_id}/materials/file", status_code=201)
async def add_material_file(
    course_id: UUID,
    request: Request,
    filename: str = Query(max_length=200),
    title: str | None = Query(default=None, max_length=200),
    subject_id: UUID | None = None,
) -> notes.MaterialOut:
    content = await _body(request)

    async def save(connection):
        await studies._own(connection, "study_course", str(course_id))
        saved = await notes.save_file(
            connection, filename, content, request.headers.get("content-type", "")
        )
        item = notes.MaterialIn.model_construct(
            title=(title or filename).strip()[:200] or "Fichero",
            url=None,
            subject_id=str(subject_id) if subject_id else None,
        )
        return await notes.add_material(connection, str(course_id), item, saved.id)

    return await _run(save)


@app.delete("/materials/{material_id}", status_code=204)
async def delete_material(material_id: UUID) -> Response:
    await _run(notes.delete_material, str(material_id))
    return Response(status_code=204)


service.serve_ui()
