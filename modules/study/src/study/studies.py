from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from study import grades, outbox

LOCAL = ZoneInfo("Europe/Madrid")

Kind = Literal["master", "degree", "course", "certification", "language", "other"]
Modality = Literal["in_person", "online", "hybrid"]
Status = Literal["planned", "active", "finished", "abandoned"]
AssessmentKind = Literal["assignment", "exam", "practical", "participation", "other"]
AssessmentStatus = Literal["pending", "submitted", "graded"]
Source = Literal["app", "tool"]


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def now() -> datetime:
    return datetime.now(LOCAL)


def today() -> date:
    return now().date()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _float(value) -> float | None:
    return None if value is None else float(value)


class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    teacher: str | None = Field(default=None, max_length=200)
    credits: float | None = Field(default=None, gt=0, le=999)
    period: str | None = Field(default=None, max_length=60)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("la asignatura necesita un nombre")
        return value

    @field_validator("teacher", "period")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _clean(value)


Track = Literal["grades", "progress", "attendance"]
ALL_TRACKS: tuple[Track, ...] = ("grades", "progress", "attendance")
LOOSE_KINDS = frozenset({"language", "other"})


def default_tracks(kind: str) -> list[Track]:
    return [] if kind in LOOSE_KINDS else list(ALL_TRACKS)


class CourseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Kind = "course"
    institution: str | None = Field(default=None, max_length=200)
    modality: Modality = "in_person"
    starts_on: date | None = None
    ends_on: date | None = None
    status: Literal["planned", "active"] = "active"
    credits: float | None = Field(default=None, gt=0, le=9999)
    hours: float | None = Field(default=None, gt=0, le=99999)
    scale_max: Literal[10, 100] = 10
    pass_mark: float | None = Field(default=None, gt=0)
    target_grade: float | None = Field(default=None, gt=0)
    tone: int = Field(default=1, ge=1, le=10)
    campus_url: str | None = Field(default=None, max_length=500)
    tz: str = "Europe/Madrid"
    note: str | None = Field(default=None, max_length=4000)
    tracks: list[Track] | None = Field(default=None, max_length=3)
    subjects: list[SubjectIn] = Field(default_factory=list, max_length=60)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("el estudio necesita un nombre")
        return value

    @field_validator("institution", "note")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("campus_url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _link(value)

    @field_validator("tz")
    @classmethod
    def _tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"{value!r} no es una zona horaria") from error
        return value

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("el estudio no puede acabar antes de empezar")
        if self.pass_mark is None:
            self.pass_mark = self.scale_max / 2
        if self.pass_mark > self.scale_max:
            raise ValueError(f"el aprobado no puede pasar de {self.scale_max}")
        if self.target_grade is not None and self.target_grade > self.scale_max:
            raise ValueError(f"el objetivo no puede pasar de {self.scale_max}")
        return self


def _link(value: str | None) -> str | None:
    value = _clean(value)
    if value is None:
        return None
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    if " " in value or "." not in value:
        raise ValueError("eso no parece un enlace")
    return value


class CourseEdit(CourseIn):
    subjects: list[SubjectIn] = Field(default_factory=list, max_length=0)
    final_grade: float | None = Field(default=None, ge=0)


class CloseIn(BaseModel):
    status: Literal["finished", "abandoned"]
    closed_on: date | None = None
    final_grade: float | None = Field(default=None, ge=0)


class AssessmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: AssessmentKind = "assignment"
    subject_id: str | None = None
    due_on: date | None = None
    due_time: time | None = None
    weight: float | None = Field(default=None, gt=0, le=100)
    min_grade: float | None = Field(default=None, ge=0)
    status: AssessmentStatus = "pending"
    grade: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("el evaluable necesita un título")
        return value

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return _clean(value)

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.due_time is not None and self.due_on is None:
            raise ValueError("una hora sin día no dice cuándo")
        if self.grade is not None:
            self.status = "graded"
        elif self.status == "graded":
            raise ValueError("calificado es con nota")
        return self


class GradeIn(BaseModel):
    grade: float | None = Field(default=None, ge=0)
    status: Literal["pending", "submitted"] = "submitted"


class RecordIn(BaseModel):
    final_grade: float | None = Field(default=None, ge=0)


class Progress(BaseModel):
    kind: Literal["credits", "hours", "subjects", "time"]
    done: float
    total: float
    ratio: float
    label: str


class Attendance(BaseModel):
    present: int
    absent: int
    unmarked: int
    past: int
    ratio: float | None


class SessionBrief(BaseModel):
    id: str
    course_id: str
    subject_id: str | None
    kind: str
    title: str
    starts_at: datetime
    ends_at: datetime
    place: str | None
    url: str | None
    status: str
    attendance: str | None
    topic: str | None
    tone: int
    course: str
    has_notes: bool = False


class AssessmentOut(BaseModel):
    id: str
    course_id: str
    subject_id: str | None
    subject: str | None
    course: str
    tone: int
    title: str
    kind: AssessmentKind
    due_on: date | None
    due_time: time | None
    weight: float | None
    min_grade: float | None
    status: AssessmentStatus
    grade: float | None
    note: str | None
    scale_max: float
    pass_mark: float
    days_left: int | None


class SubjectOut(BaseModel):
    id: str
    course_id: str
    name: str
    teacher: str | None
    credits: float | None
    period: str | None
    final_grade: float | None
    position: int
    grade: grades.Grade
    assessments: int


class CourseOut(BaseModel):
    id: str
    name: str
    kind: Kind
    institution: str | None
    modality: Modality
    starts_on: date | None
    ends_on: date | None
    status: Status
    credits: float | None
    hours: float | None
    scale_max: float
    pass_mark: float
    target_grade: float | None
    final_grade: float | None
    tone: int
    campus_url: str | None
    tz: str
    note: str | None
    closed_on: date | None
    has_certificate: bool
    certificate_name: str | None
    tracks: list[Track]
    average: grades.CourseGrade
    grade: grades.Grade | None
    progress: Progress | None
    attendance: Attendance
    subjects: int
    next_session: SessionBrief | None


class CourseDetail(BaseModel):
    course: CourseOut
    subjects: list[SubjectOut]
    assessments: list[AssessmentOut]


COURSES = """
    select c.*, a.filename as certificate_name
    from study.study_course c
    left join study.study_attachment a on a.id = c.certificate_id
"""


async def _own(connection: AsyncConnection, table: str, id_: str | None) -> None:
    if id_ is None:
        return
    try:
        found = await connection.scalar(
            text(f"select 1 from study.{table} where id = cast(:id as uuid)"), {"id": id_}
        )
    except Exception as error:  # noqa: BLE001 -- un id que no es uuid es un id que no está
        raise NotFound(id_) from error
    if not found:
        raise NotFound(id_)


async def _load(connection: AsyncConnection, course_ids: list) -> dict:
    if not course_ids:
        return {"subjects": [], "assessments": [], "sessions": [], "next": {}}
    params = {"ids": [str(i) for i in course_ids]}
    subjects = (
        await connection.execute(
            text("""
                select s.*, (select count(*) from study.study_assessment a where a.subject_id = s.id)
                       as assessments
                from study.study_subject s
                where s.course_id = any(cast(:ids as uuid[]))
                order by s.position, s.created_at
            """),
            params,
        )
    ).all()
    assessments = (
        await connection.execute(
            text("""
                select * from study.study_assessment
                where course_id = any(cast(:ids as uuid[]))
            """),
            params,
        )
    ).all()
    sessions = (
        await connection.execute(
            text("""
                select course_id,
                       count(*) filter (where attendance = 'present') as present,
                       count(*) filter (where attendance = 'absent') as absent,
                       count(*) filter (where attendance is null) as unmarked,
                       count(*) as past,
                       coalesce(sum(extract(epoch from ends_at - starts_at))
                                filter (where attendance is distinct from 'absent'), 0) / 3600.0
                           as hours
                from study.study_session
                where course_id = any(cast(:ids as uuid[]))
                  and status = 'scheduled' and ends_at <= now()
                group by course_id
            """),
            params,
        )
    ).all()
    upcoming = (
        await connection.execute(
            text(f"""
                select distinct on (s.course_id) {SESSION_COLUMNS}
                {SESSION_FROM}
                where s.course_id = any(cast(:ids as uuid[]))
                  and s.status = 'scheduled' and s.ends_at > now()
                order by s.course_id, s.starts_at
            """),
            params,
        )
    ).all()
    return {
        "subjects": subjects,
        "assessments": assessments,
        "sessions": {row.course_id: row for row in sessions},
        "next": {row.course_id: session_brief(row) for row in upcoming},
    }


def _items(rows) -> list[grades.Item]:
    return [
        grades.Item(
            title=row.title,
            weight=_float(row.weight),
            grade=_float(row.grade),
            min_grade=_float(row.min_grade),
        )
        for row in rows
    ]


def _subject_out(row, course, assessments) -> SubjectOut:
    own = [a for a in assessments if a.subject_id == row.id]
    grade = grades.compute(
        _items(own),
        scale_max=float(course.scale_max),
        pass_mark=float(course.pass_mark),
        target=_float(course.target_grade),
        record=_float(row.final_grade),
    )
    return SubjectOut(
        id=str(row.id),
        course_id=str(row.course_id),
        name=row.name,
        teacher=row.teacher,
        credits=_float(row.credits),
        period=row.period,
        final_grade=_float(row.final_grade),
        position=row.position,
        grade=grade,
        assessments=row.assessments,
    )


def _progress(course, subjects: list[SubjectOut], hours_done: float) -> Progress | None:
    subject_credits = sum(s.credits or 0 for s in subjects)
    total_credits = _float(course.credits) or subject_credits
    passed = [s for s in subjects if s.grade.verdict == "passed"]
    if total_credits:
        done = sum(s.credits or 0 for s in passed)
        return Progress(
            kind="credits",
            done=done,
            total=total_credits,
            ratio=min(done / total_credits, 1.0),
            label=f"{grades.number(done, 100)} de {grades.number(total_credits, 100)} créditos",
        )
    if course.hours:
        total = float(course.hours)
        return Progress(
            kind="hours",
            done=round(hours_done, 1),
            total=total,
            ratio=min(hours_done / total, 1.0),
            label=f"{grades.number(hours_done)} de {grades.number(total, 100)} horas",
        )
    if subjects:
        return Progress(
            kind="subjects",
            done=len(passed),
            total=len(subjects),
            ratio=len(passed) / len(subjects),
            label=f"{len(passed)} de {len(subjects)} asignaturas aprobadas",
        )
    if course.starts_on and course.ends_on and course.ends_on > course.starts_on:
        span = (course.ends_on - course.starts_on).days + 1
        gone = min(max((today() - course.starts_on).days + 1, 0), span)
        week, weeks = max(1, -(-gone // 7)), max(1, -(-span // 7))
        return Progress(
            kind="time",
            done=gone,
            total=span,
            ratio=gone / span,
            label=f"Semana {min(week, weeks)} de {weeks}" if gone else "Aún no ha empezado",
        )
    return None


def _course_out(row, loaded: dict) -> CourseOut:
    subjects = [
        _subject_out(s, row, loaded["assessments"])
        for s in loaded["subjects"]
        if s.course_id == row.id
    ]
    own = [a for a in loaded["assessments"] if a.course_id == row.id]
    grade = None
    if not subjects:
        grade = grades.compute(
            _items(own),
            scale_max=float(row.scale_max),
            pass_mark=float(row.pass_mark),
            target=_float(row.target_grade),
            record=_float(row.final_grade),
        )
    average = grades.course_average(
        [
            grades.SubjectResult(
                credits=s.credits, final=s.grade.final, passed=s.grade.verdict == "passed"
            )
            for s in subjects
        ],
        record=_float(row.final_grade),
    )
    if not subjects and grade is not None and grade.final is not None and average.average is None:
        average = grades.CourseGrade(
            average=grade.final, average_source="assessments", counted=0, subjects=0
        )
    sessions = loaded["sessions"].get(row.id)
    past = sessions.past if sessions else 0
    present = sessions.present if sessions else 0
    marked = present + (sessions.absent if sessions else 0)
    attendance = Attendance(
        present=present,
        absent=sessions.absent if sessions else 0,
        unmarked=sessions.unmarked if sessions else 0,
        past=past,
        ratio=(present / marked) if marked else None,
    )
    return CourseOut(
        id=str(row.id),
        name=row.name,
        kind=row.kind,
        institution=row.institution,
        modality=row.modality,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        status=row.status,
        credits=_float(row.credits),
        hours=_float(row.hours),
        scale_max=float(row.scale_max),
        pass_mark=float(row.pass_mark),
        target_grade=_float(row.target_grade),
        final_grade=_float(row.final_grade),
        tone=row.tone,
        campus_url=row.campus_url,
        tz=row.tz,
        note=row.note,
        closed_on=row.closed_on,
        has_certificate=row.certificate_id is not None,
        certificate_name=row.certificate_name,
        tracks=[one for one in ALL_TRACKS if one in row.tracks],
        average=average,
        grade=grade,
        progress=_progress(row, subjects, float(sessions.hours) if sessions else 0.0),
        attendance=attendance,
        subjects=len(subjects),
        next_session=loaded["next"].get(row.id),
    )


ORDER = """
    order by case c.status when 'active' then 0 when 'planned' then 1 else 2 end,
             coalesce(c.closed_on, c.starts_on) desc nulls last, c.created_at desc
"""


async def courses(
    connection: AsyncConnection, scope: Literal["current", "archive", "all"] = "current"
) -> list[CourseOut]:
    where = {
        "current": "where c.status in ('planned', 'active')",
        "archive": "where c.status in ('finished', 'abandoned')",
        "all": "",
    }[scope]
    rows = (await connection.execute(text(f"{COURSES} {where} {ORDER}"))).all()
    loaded = await _load(connection, [row.id for row in rows])
    return [_course_out(row, loaded) for row in rows]


async def course(connection: AsyncConnection, course_id: str) -> CourseDetail:
    await _own(connection, "study_course", course_id)
    row = (
        await connection.execute(
            text(f"{COURSES} where c.id = cast(:id as uuid)"), {"id": course_id}
        )
    ).one()
    loaded = await _load(connection, [row.id])
    out = _course_out(row, loaded)
    subjects = [
        _subject_out(s, row, loaded["assessments"])
        for s in loaded["subjects"]
        if s.course_id == row.id
    ]
    return CourseDetail(
        course=out,
        subjects=subjects,
        assessments=await assessments(connection, course_id=course_id),
    )


INSERT_COURSE = text("""
    insert into study.study_course
        (name, kind, institution, modality, starts_on, ends_on, status, credits, hours, scale_max,
         pass_mark, target_grade, tone, campus_url, tz, note, source, tracks)
    values
        (:name, :kind, :institution, :modality, :starts_on, :ends_on, :status, :credits, :hours,
         :scale_max, :pass_mark, :target_grade, :tone, :campus_url, :tz, :note, :source, :tracks)
    returning id
""")


def _course_params(course: CourseIn) -> dict:
    return {
        "name": course.name,
        "kind": course.kind,
        "institution": course.institution,
        "modality": course.modality,
        "starts_on": course.starts_on,
        "ends_on": course.ends_on,
        "status": course.status,
        "credits": course.credits,
        "hours": course.hours,
        "scale_max": course.scale_max,
        "pass_mark": course.pass_mark,
        "target_grade": course.target_grade,
        "tone": course.tone,
        "campus_url": course.campus_url,
        "tz": course.tz,
        "note": course.note,
    }


async def create_course(
    connection: AsyncConnection, new: CourseIn, source: Source = "app"
) -> CourseDetail:
    tracks = sorted(set(new.tracks)) if new.tracks is not None else default_tracks(new.kind)
    course_id = await connection.scalar(
        INSERT_COURSE, {**_course_params(new), "source": source, "tracks": tracks}
    )
    for position, subject in enumerate(new.subjects):
        await _insert_subject(connection, str(course_id), subject, position)
    await outbox.course_changed(connection, str(course_id))
    return await course(connection, str(course_id))


async def update_course(
    connection: AsyncConnection, course_id: str, edit: CourseEdit
) -> CourseDetail:
    await _own(connection, "study_course", course_id)
    current = (
        await connection.execute(
            text("select status, name from study.study_course where id = :id"), {"id": course_id}
        )
    ).one()
    if edit.final_grade is not None and edit.final_grade > edit.scale_max:
        raise Conflict(f"la nota no puede pasar de {edit.scale_max}")
    params = _course_params(edit)
    if current.status in ("finished", "abandoned"):
        params["status"] = current.status
    await _check_record_grades(connection, course_id, edit.scale_max)
    from study.apuntes import ROOT, clean

    await connection.execute(
        text("""
            update study.study_course
            set notes_folder = :folder
            where id = :id and notes_folder is null and name <> :name
        """),
        {"folder": f"{ROOT}/{clean(current.name)}", "name": edit.name, "id": course_id},
    )
    await connection.execute(
        text("""
            update study.study_course
            set name = :name, kind = :kind, institution = :institution, modality = :modality,
                starts_on = :starts_on, ends_on = :ends_on, status = :status, credits = :credits,
                hours = :hours, scale_max = :scale_max, pass_mark = :pass_mark,
                target_grade = :target_grade, final_grade = :final_grade, tone = :tone,
                campus_url = :campus_url, tz = :tz, note = :note,
                tracks = coalesce(cast(:tracks as text[]), tracks), updated_at = now()
            where id = :id
        """),
        {
            **params,
            "final_grade": edit.final_grade,
            "id": course_id,
            "tracks": sorted(set(edit.tracks)) if edit.tracks is not None else None,
        },
    )
    await outbox.course_changed(connection, course_id)
    return await course(connection, course_id)


async def _check_record_grades(
    connection: AsyncConnection, course_id: str, scale_max: float
) -> None:
    over = await connection.scalar(
        text("""
            select count(*) from (
                select grade as value from study.study_assessment where course_id = :id
                union all
                select final_grade from study.study_subject where course_id = :id
            ) grades
            where value > :max
        """),
        {"id": course_id, "max": scale_max},
    )
    if over:
        raise Conflict(f"hay notas por encima de {grades.number(scale_max, 100)}: cámbialas antes")


async def close_course(connection: AsyncConnection, course_id: str, close: CloseIn) -> CourseDetail:
    await _own(connection, "study_course", course_id)
    scale = await connection.scalar(
        text("select scale_max from study.study_course where id = :id"), {"id": course_id}
    )
    if close.final_grade is not None and close.final_grade > float(scale):
        raise Conflict(f"la nota no puede pasar de {grades.number(float(scale), 100)}")
    await connection.execute(
        text("""
            update study.study_course
            set status = :status, closed_on = :closed_on,
                final_grade = coalesce(:final_grade, final_grade), updated_at = now()
            where id = :id
        """),
        {
            "status": close.status,
            "closed_on": close.closed_on or today(),
            "final_grade": close.final_grade,
            "id": course_id,
        },
    )
    await outbox.course_changed(connection, course_id)
    return await course(connection, course_id)


async def reopen_course(connection: AsyncConnection, course_id: str) -> CourseDetail:
    await _own(connection, "study_course", course_id)
    await connection.execute(
        text("""
            update study.study_course set status = 'active', closed_on = null, updated_at = now()
            where id = :id
        """),
        {"id": course_id},
    )
    await outbox.course_changed(connection, course_id)
    return await course(connection, course_id)


async def delete_course(connection: AsyncConnection, course_id: str) -> None:
    await _own(connection, "study_course", course_id)
    sessions = (
        await connection.execute(
            text(f"select {SESSION_COLUMNS}, c.tz {SESSION_FROM} where s.course_id = :id"),
            {"id": course_id},
        )
    ).all()
    for row in sessions:
        await outbox.enqueue(connection, "study.session", outbox.session_payload(row, removed=True))
    for (assessment_id,) in (
        await connection.execute(
            text("select id from study.study_assessment where course_id = :id"), {"id": course_id}
        )
    ).all():
        await outbox.assessment_changed(connection, str(assessment_id), removed=True)
    files = (
        (
            await connection.execute(
                text("""
                select attachment_id from study.study_material where course_id = :id
                  and attachment_id is not null
                union
                select l.attachment_id from study.study_attachment_link l
                join study.study_note n on n.id = l.note_id where n.course_id = :id
                union
                select l.attachment_id from study.study_attachment_link l
                join study.study_session s on s.id = l.session_id where s.course_id = :id
                union
                select certificate_id from study.study_course where id = :id
                  and certificate_id is not null
            """),
                {"id": course_id},
            )
        )
        .scalars()
        .all()
    )
    await connection.execute(
        text("delete from study.study_course where id = :id"), {"id": course_id}
    )
    if files:
        await connection.execute(
            text("delete from study.study_attachment where id = any(cast(:ids as uuid[]))"),
            {"ids": [str(f) for f in files]},
        )
    await outbox.enqueue(connection, "study.course", {"id": course_id, "status": "removed"})


async def _insert_subject(
    connection: AsyncConnection, course_id: str, subject: SubjectIn, position: int
) -> str:
    return str(
        await connection.scalar(
            text("""
                insert into study.study_subject (course_id, name, teacher, credits, period, position)
                values (:course_id, :name, :teacher, :credits, :period, :position)
                returning id
            """),
            {
                "course_id": course_id,
                "name": subject.name,
                "teacher": subject.teacher,
                "credits": subject.credits,
                "period": subject.period,
                "position": position,
            },
        )
    )


async def add_subject(
    connection: AsyncConnection, course_id: str, subject: SubjectIn
) -> SubjectOut:
    await _own(connection, "study_course", course_id)
    position = await connection.scalar(
        text(
            "select coalesce(max(position) + 1, 0) from study.study_subject where course_id = :id"
        ),
        {"id": course_id},
    )
    subject_id = await _insert_subject(connection, course_id, subject, position)
    return await subject_summary(connection, subject_id)


async def subject_summary(connection: AsyncConnection, subject_id: str) -> SubjectOut:
    await _own(connection, "study_subject", subject_id)
    course_id = await connection.scalar(
        text("select course_id from study.study_subject where id = :id"), {"id": subject_id}
    )
    course_row = (
        await connection.execute(text(f"{COURSES} where c.id = :id"), {"id": course_id})
    ).one()
    loaded = await _load(connection, [course_id])
    row = next(s for s in loaded["subjects"] if str(s.id) == subject_id)
    return _subject_out(row, course_row, loaded["assessments"])


async def update_subject(
    connection: AsyncConnection, subject_id: str, subject: SubjectIn
) -> SubjectOut:
    await _own(connection, "study_subject", subject_id)
    await connection.execute(
        text("""
            update study.study_subject
            set name = :name, teacher = :teacher, credits = :credits, period = :period,
                updated_at = now()
            where id = :id
        """),
        {
            "name": subject.name,
            "teacher": subject.teacher,
            "credits": subject.credits,
            "period": subject.period,
            "id": subject_id,
        },
    )
    return await subject_summary(connection, subject_id)


async def record_grade(
    connection: AsyncConnection, subject_id: str, record: RecordIn
) -> SubjectOut:
    await _own(connection, "study_subject", subject_id)
    scale = await connection.scalar(
        text("""
            select c.scale_max from study.study_subject s
            join study.study_course c on c.id = s.course_id where s.id = :id
        """),
        {"id": subject_id},
    )
    if record.final_grade is not None and record.final_grade > float(scale):
        raise Conflict(f"la nota no puede pasar de {grades.number(float(scale), 100)}")
    await connection.execute(
        text(
            "update study.study_subject set final_grade = :grade, updated_at = now() where id = :id"
        ),
        {"grade": record.final_grade, "id": subject_id},
    )
    return await subject_summary(connection, subject_id)


async def move_subject(connection: AsyncConnection, subject_id: str, position: int) -> None:
    await _own(connection, "study_subject", subject_id)
    course_id = await connection.scalar(
        text("select course_id from study.study_subject where id = :id"), {"id": subject_id}
    )
    ids = (
        (
            await connection.execute(
                text("""
                select id from study.study_subject where course_id = :course and id <> :id
                order by position, created_at
            """),
                {"course": course_id, "id": subject_id},
            )
        )
        .scalars()
        .all()
    )
    ids = [str(i) for i in ids]
    ids.insert(max(0, min(position, len(ids))), subject_id)
    for index, one in enumerate(ids):
        await connection.execute(
            text("update study.study_subject set position = :p where id = :id"),
            {"p": index, "id": one},
        )


async def delete_subject(connection: AsyncConnection, subject_id: str) -> None:
    await _own(connection, "study_subject", subject_id)
    sessions = (
        await connection.execute(
            text(f"select {SESSION_COLUMNS}, c.tz {SESSION_FROM} where s.subject_id = :id"),
            {"id": subject_id},
        )
    ).all()
    for row in sessions:
        await outbox.enqueue(connection, "study.session", outbox.session_payload(row, removed=True))
    for (assessment_id,) in (
        await connection.execute(
            text("select id from study.study_assessment where subject_id = :id"), {"id": subject_id}
        )
    ).all():
        await outbox.assessment_changed(connection, str(assessment_id), removed=True)
    await connection.execute(
        text("delete from study.study_subject where id = :id"), {"id": subject_id}
    )


ASSESSMENTS = """
    select a.*, c.name as course, c.tone, c.scale_max, c.pass_mark, j.name as subject
    from study.study_assessment a
    join study.study_course c on c.id = a.course_id
    left join study.study_subject j on j.id = a.subject_id
"""


def assessment_out(row) -> AssessmentOut:
    return AssessmentOut(
        id=str(row.id),
        course_id=str(row.course_id),
        subject_id=str(row.subject_id) if row.subject_id else None,
        subject=row.subject,
        course=row.course,
        tone=row.tone,
        title=row.title,
        kind=row.kind,
        due_on=row.due_on,
        due_time=row.due_time,
        weight=_float(row.weight),
        min_grade=_float(row.min_grade),
        status=row.status,
        grade=_float(row.grade),
        note=row.note,
        scale_max=float(row.scale_max),
        pass_mark=float(row.pass_mark),
        days_left=(row.due_on - today()).days if row.due_on else None,
    )


async def assessments(
    connection: AsyncConnection,
    *,
    course_id: str | None = None,
    subject_id: str | None = None,
    pending_only: bool = False,
    since: date | None = None,
    until: date | None = None,
) -> list[AssessmentOut]:
    where, params = [], {}
    if course_id:
        where.append("a.course_id = cast(:course as uuid)")
        params["course"] = course_id
    if subject_id:
        where.append("a.subject_id = cast(:subject as uuid)")
        params["subject"] = subject_id
    if pending_only:
        where.append("a.status = 'pending' and c.status in ('planned', 'active')")
    if since:
        where.append("a.due_on >= :since")
        params["since"] = since
    if until:
        where.append("a.due_on < :until")
        params["until"] = until
    clause = ("where " + " and ".join(where)) if where else ""
    rows = (
        await connection.execute(
            text(
                f"{ASSESSMENTS} {clause} "
                "order by a.due_on nulls last, a.due_time nulls last, a.title"
            ),
            params,
        )
    ).all()
    return [assessment_out(row) for row in rows]


async def assessment(connection: AsyncConnection, assessment_id: str) -> AssessmentOut:
    await _own(connection, "study_assessment", assessment_id)
    row = (
        await connection.execute(text(f"{ASSESSMENTS} where a.id = :id"), {"id": assessment_id})
    ).one()
    return assessment_out(row)


async def _check_assessment(
    connection: AsyncConnection, course_id: str, item: AssessmentIn
) -> None:
    if item.subject_id:
        await _own(connection, "study_subject", item.subject_id)
        owner = await connection.scalar(
            text("select course_id from study.study_subject where id = :id"),
            {"id": item.subject_id},
        )
        if str(owner) != course_id:
            raise Conflict("esa asignatura es de otro estudio")
    scale = float(
        await connection.scalar(
            text("select scale_max from study.study_course where id = :id"), {"id": course_id}
        )
    )
    for label, value in (("la nota", item.grade), ("la nota mínima", item.min_grade)):
        if value is not None and value > scale:
            raise Conflict(f"{label} no puede pasar de {grades.number(scale, 100)}")


async def add_assessment(
    connection: AsyncConnection, course_id: str, item: AssessmentIn, source: Source = "app"
) -> AssessmentOut:
    await _own(connection, "study_course", course_id)
    await _check_assessment(connection, course_id, item)
    assessment_id = await connection.scalar(
        text("""
            insert into study.study_assessment
                (course_id, subject_id, title, kind, due_on, due_time, weight, min_grade, status,
                 grade, note, source)
            values (:course_id, :subject_id, :title, :kind, :due_on, :due_time, :weight,
                    :min_grade, :status, :grade, :note, :source)
            returning id
        """),
        {**_assessment_params(item), "course_id": course_id, "source": source},
    )
    await outbox.assessment_changed(connection, str(assessment_id))
    return await assessment(connection, str(assessment_id))


def _assessment_params(item: AssessmentIn) -> dict:
    return {
        "subject_id": item.subject_id,
        "title": item.title,
        "kind": item.kind,
        "due_on": item.due_on,
        "due_time": item.due_time,
        "weight": item.weight,
        "min_grade": item.min_grade,
        "status": item.status,
        "grade": item.grade,
        "note": item.note,
    }


async def update_assessment(
    connection: AsyncConnection, assessment_id: str, item: AssessmentIn
) -> AssessmentOut:
    await _own(connection, "study_assessment", assessment_id)
    course_id = str(
        await connection.scalar(
            text("select course_id from study.study_assessment where id = :id"),
            {"id": assessment_id},
        )
    )
    await _check_assessment(connection, course_id, item)
    await connection.execute(
        text("""
            update study.study_assessment
            set subject_id = :subject_id, title = :title, kind = :kind, due_on = :due_on,
                due_time = :due_time, weight = :weight, min_grade = :min_grade, status = :status,
                grade = :grade, note = :note, updated_at = now()
            where id = :id
        """),
        {**_assessment_params(item), "id": assessment_id},
    )
    await outbox.assessment_changed(connection, assessment_id, stamp=datetime.now(UTC))
    return await assessment(connection, assessment_id)


async def grade_assessment(
    connection: AsyncConnection, assessment_id: str, given: GradeIn
) -> AssessmentOut:
    current = await assessment(connection, assessment_id)
    if given.grade is not None and given.grade > current.scale_max:
        raise Conflict(f"la nota no puede pasar de {grades.number(current.scale_max, 100)}")
    await connection.execute(
        text("""
            update study.study_assessment
            set grade = :grade, status = :status, updated_at = now()
            where id = :id
        """),
        {
            "grade": given.grade,
            "status": "graded" if given.grade is not None else given.status,
            "id": assessment_id,
        },
    )
    await outbox.assessment_changed(connection, assessment_id)
    return await assessment(connection, assessment_id)


async def delete_assessment(connection: AsyncConnection, assessment_id: str) -> None:
    await _own(connection, "study_assessment", assessment_id)
    await outbox.assessment_changed(connection, assessment_id, removed=True)
    await connection.execute(
        text("delete from study.study_assessment where id = :id"), {"id": assessment_id}
    )


SESSION_COLUMNS = """
    s.id, s.course_id, s.subject_id, s.kind, s.title, s.starts_at, s.ends_at, s.place, s.url,
    s.status, s.attendance, s.topic, c.tone, c.name as course, j.name as subject,
    exists (select 1 from study.study_note n where n.session_id = s.id) as has_notes
"""
SESSION_FROM = """
    from study.study_session s
    join study.study_course c on c.id = s.course_id
    left join study.study_subject j on j.id = s.subject_id
"""


def session_brief(row) -> SessionBrief:
    return SessionBrief(
        id=str(row.id),
        course_id=str(row.course_id),
        subject_id=str(row.subject_id) if row.subject_id else None,
        kind=row.kind,
        title=row.title or row.subject or row.course,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        place=row.place,
        url=row.url,
        status=row.status,
        attendance=row.attendance,
        topic=row.topic,
        tone=row.tone,
        course=row.course,
        has_notes=row.has_notes,
    )


class Day(BaseModel):
    date: date
    today: bool
    sessions: list[SessionBrief]
    assessments: list[AssessmentOut]


class Home(BaseModel):
    week_start: date
    days: list[Day]
    upcoming: list[AssessmentOut]
    courses: list[CourseOut]
    archived: int


async def home(connection: AsyncConnection, week_of: date | None = None) -> Home:
    day = week_of or today()
    monday = day - timedelta(days=day.weekday())
    start = datetime.combine(monday, time(0), tzinfo=LOCAL)
    end = start + timedelta(days=7)
    rows = (
        await connection.execute(
            text(f"""
                select {SESSION_COLUMNS} {SESSION_FROM}
                where s.starts_at >= :start and s.starts_at < :end
                  and c.status in ('planned', 'active')
                order by s.starts_at
            """),
            {"start": start, "end": end},
        )
    ).all()
    sessions = [session_brief(row) for row in rows]
    current_courses = await courses(connection)
    open_ids = {c.id for c in current_courses}
    dated = await assessments(connection, since=monday, until=monday + timedelta(days=7))
    dated = [a for a in dated if a.course_id in open_ids]
    days = []
    for offset in range(7):
        current = monday + timedelta(days=offset)
        days.append(
            Day(
                date=current,
                today=current == today(),
                sessions=[s for s in sessions if s.starts_at.astimezone(LOCAL).date() == current],
                assessments=[a for a in dated if a.due_on == current],
            )
        )
    pending = await assessments(connection, pending_only=True)
    upcoming = [a for a in pending if a.due_on is not None and a.days_left is not None]
    upcoming = [a for a in upcoming if a.days_left >= -14][:12]
    archived = await connection.scalar(
        text("select count(*) from study.study_course where status in ('finished', 'abandoned')")
    )
    return Home(
        week_start=monday,
        days=days,
        upcoming=upcoming,
        courses=current_courses,
        archived=archived,
    )
