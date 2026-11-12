from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from study.studies import Conflict, NotFound, _link, _own

FILE_LIMIT = 20 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
INLINE_TYPES = IMAGE_TYPES | {"application/pdf", "text/plain"}
IMAGE_LINK = re.compile(r"/api/study/attachments/([0-9a-f-]{36})")


class NoteIn(BaseModel):
    course_id: str
    subject_id: str | None = None
    session_id: str | None = None
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=500000)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return value.strip()


class NoteEdit(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=500000)
    subject_id: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return value.strip()


class NoteBrief(BaseModel):
    id: str
    course_id: str
    subject_id: str | None
    session_id: str | None
    title: str
    excerpt: str
    course: str
    subject: str | None
    tone: int
    session_start: datetime | None
    created_at: datetime
    updated_at: datetime
    words: int
    folder: str = ""


class Note(NoteBrief):
    body: str


class Hit(NoteBrief):
    fragment: str
    rank: float


class MaterialIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    subject_id: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("el material necesita un nombre")
        return value

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return _link(value)


class MaterialOut(BaseModel):
    id: str
    course_id: str
    subject_id: str | None
    subject: str | None
    title: str
    url: str | None
    attachment_id: str | None
    filename: str | None
    content_type: str | None
    size: int | None
    created_at: datetime


class AttachmentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    is_image: bool
    url: str
    created_at: datetime


class Place(BaseModel):
    note_id: str | None = None
    session_id: str | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.note_id is None) == (self.session_id is None):
            raise ValueError("un fichero es de unos apuntes o de una clase")
        return self


async def _place_note(connection: AsyncConnection, item: NoteIn | NoteEdit, course_id: str) -> None:
    if item.subject_id:
        await _own(connection, "study_subject", item.subject_id)
        owner = await connection.scalar(
            text("select course_id from study.study_subject where id = :id"),
            {"id": item.subject_id},
        )
        if str(owner) != course_id:
            raise Conflict("esa asignatura es de otro estudio")


async def _claim_images(connection: AsyncConnection, note_id: str, body: str) -> None:
    ids = list(dict.fromkeys(IMAGE_LINK.findall(body)))
    if not ids:
        return
    await connection.execute(
        text("""
            insert into study.study_attachment_link (attachment_id, note_id)
            select a.id, :note from study.study_attachment a
            where a.id = any(cast(:ids as uuid[]))
              and not exists (
                  select 1 from study.study_attachment_link l where l.attachment_id = a.id
              )
              and not exists (select 1 from study.study_material m where m.attachment_id = a.id)
              and not exists (select 1 from study.study_course c where c.certificate_id = a.id)
        """),
        {"note": note_id, "ids": ids},
    )


async def delete_note(connection: AsyncConnection, note_id: str) -> None:
    await _own(connection, "study_note", note_id)
    files = (
        (
            await connection.execute(
                text("select attachment_id from study.study_attachment_link where note_id = :id"),
                {"id": note_id},
            )
        )
        .scalars()
        .all()
    )
    await connection.execute(text("delete from study.study_note where id = :id"), {"id": note_id})
    if files:
        await connection.execute(
            text("delete from study.study_attachment where id = any(cast(:ids as uuid[]))"),
            {"ids": [str(f) for f in files]},
        )


def _safe_name(filename: str) -> str:
    name = re.sub(r"[\x00-\x1f\"\\/]+", "_", filename).strip() or "fichero"
    return name[:200]


def _attachment_out(row) -> AttachmentOut:
    return AttachmentOut(
        id=str(row.id),
        filename=row.filename,
        content_type=row.content_type,
        size=row.size,
        is_image=row.content_type in IMAGE_TYPES,
        url=f"/api/study/attachments/{row.id}",
        created_at=row.created_at,
    )


def _sniff(content: bytes, declared: str) -> str:
    signatures = {
        b"\x89PNG\r\n\x1a\n": "image/png",
        b"\xff\xd8\xff": "image/jpeg",
        b"GIF87a": "image/gif",
        b"GIF89a": "image/gif",
        b"%PDF-": "application/pdf",
    }
    for prefix, kind in signatures.items():
        if content.startswith(prefix):
            return kind
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    declared = (declared or "").split(";")[0].strip().lower()
    if declared in IMAGE_TYPES or declared == "application/pdf":
        return "application/octet-stream"
    if not re.fullmatch(r"[a-z]+/[a-z0-9.+-]+", declared):
        return "application/octet-stream"
    return declared


async def save_file(
    connection: AsyncConnection, filename: str, content: bytes, declared: str
) -> AttachmentOut:
    if not content:
        raise Conflict("el fichero está vacío")
    if len(content) > FILE_LIMIT:
        raise Conflict("el fichero pasa de 20 MB")
    row = (
        await connection.execute(
            text("""
                insert into study.study_attachment (filename, content_type, size, content)
                values (:name, :kind, :size, :content)
                returning id, filename, content_type, size, created_at
            """),
            {
                "name": _safe_name(filename),
                "kind": _sniff(content, declared),
                "size": len(content),
                "content": content,
            },
        )
    ).one()
    return _attachment_out(row)


async def attach(connection: AsyncConnection, attachment_id: str, place: Place) -> AttachmentOut:
    await _own(connection, "study_attachment", attachment_id)
    if place.note_id:
        await _own(connection, "study_note", place.note_id)
    if place.session_id:
        await _own(connection, "study_session", place.session_id)
    await connection.execute(
        text("""
            insert into study.study_attachment_link (attachment_id, note_id, session_id)
            values (:id, :note, :session)
            on conflict (attachment_id) do update
                set note_id = excluded.note_id, session_id = excluded.session_id
        """),
        {"id": attachment_id, "note": place.note_id, "session": place.session_id},
    )
    row = (
        await connection.execute(
            text(
                "select id, filename, content_type, size, created_at from study.study_attachment "
                "where id = :id"
            ),
            {"id": attachment_id},
        )
    ).one()
    return _attachment_out(row)


async def session_files(connection: AsyncConnection, session_id: str) -> list[AttachmentOut]:
    await _own(connection, "study_session", session_id)
    rows = (
        await connection.execute(
            text("""
                select a.id, a.filename, a.content_type, a.size, a.created_at
                from study.study_attachment a
                join study.study_attachment_link l on l.attachment_id = a.id
                where l.session_id = :id
                order by a.created_at
            """),
            {"id": session_id},
        )
    ).all()
    return [_attachment_out(row) for row in rows]


async def read_file(
    connection: AsyncConnection, attachment_id: str
) -> tuple[str, str, bytes, bool]:
    await _own(connection, "study_attachment", attachment_id)
    row = (
        await connection.execute(
            text(
                "select filename, content_type, content from study.study_attachment where id = :id"
            ),
            {"id": attachment_id},
        )
    ).one()
    return row.filename, row.content_type, bytes(row.content), row.content_type in INLINE_TYPES


async def delete_file(connection: AsyncConnection, attachment_id: str) -> None:
    await _own(connection, "study_attachment", attachment_id)
    await connection.execute(
        text("update study.study_course set certificate_id = null where certificate_id = :id"),
        {"id": attachment_id},
    )
    await connection.execute(
        text("delete from study.study_attachment where id = :id"), {"id": attachment_id}
    )


async def set_certificate(connection: AsyncConnection, course_id: str, attachment_id: str) -> None:
    await _own(connection, "study_course", course_id)
    await _own(connection, "study_attachment", attachment_id)
    previous = await connection.scalar(
        text("select certificate_id from study.study_course where id = :id"), {"id": course_id}
    )
    await connection.execute(
        text(
            "update study.study_course set certificate_id = :file, updated_at = now() where id = :id"
        ),
        {"file": attachment_id, "id": course_id},
    )
    if previous and str(previous) != attachment_id:
        await connection.execute(
            text("delete from study.study_attachment where id = :id"), {"id": previous}
        )


MATERIALS = """
    select m.id, m.course_id, m.subject_id, m.title, m.url, m.attachment_id, m.created_at,
           j.name as subject, a.filename, a.content_type, a.size
    from study.study_material m
    left join study.study_subject j on j.id = m.subject_id
    left join study.study_attachment a on a.id = m.attachment_id
"""


def _material_out(row) -> MaterialOut:
    return MaterialOut(
        id=str(row.id),
        course_id=str(row.course_id),
        subject_id=str(row.subject_id) if row.subject_id else None,
        subject=row.subject,
        title=row.title,
        url=row.url,
        attachment_id=str(row.attachment_id) if row.attachment_id else None,
        filename=row.filename,
        content_type=row.content_type,
        size=row.size,
        created_at=row.created_at,
    )


async def materials(
    connection: AsyncConnection, *, course_id: str | None = None, subject_id: str | None = None
) -> list[MaterialOut]:
    field, value = ("m.subject_id", subject_id) if subject_id else ("m.course_id", course_id)
    rows = (
        await connection.execute(
            text(f"{MATERIALS} where {field} = cast(:id as uuid) order by m.created_at desc"),
            {"id": value},
        )
    ).all()
    return [_material_out(row) for row in rows]


async def add_material(
    connection: AsyncConnection,
    course_id: str,
    item: MaterialIn,
    attachment_id: str | None = None,
) -> MaterialOut:
    await _own(connection, "study_course", course_id)
    if item.subject_id:
        await _own(connection, "study_subject", item.subject_id)
        owner = await connection.scalar(
            text("select course_id from study.study_subject where id = :id"),
            {"id": item.subject_id},
        )
        if str(owner) != course_id:
            raise Conflict("esa asignatura es de otro estudio")
    if (item.url is None) == (attachment_id is None):
        raise Conflict("un material es un enlace o un fichero")
    if attachment_id:
        await _own(connection, "study_attachment", attachment_id)
    material_id = await connection.scalar(
        text("""
            insert into study.study_material (course_id, subject_id, title, url, attachment_id)
            values (:course, :subject, :title, :url, :file)
            returning id
        """),
        {
            "course": course_id,
            "subject": item.subject_id,
            "title": item.title,
            "url": item.url,
            "file": attachment_id,
        },
    )
    row = (
        await connection.execute(text(f"{MATERIALS} where m.id = :id"), {"id": material_id})
    ).one()
    return _material_out(row)


async def delete_material(connection: AsyncConnection, material_id: str) -> None:
    await _own(connection, "study_material", material_id)
    attachment_id = await connection.scalar(
        text("select attachment_id from study.study_material where id = :id"), {"id": material_id}
    )
    await connection.execute(
        text("delete from study.study_material where id = :id"), {"id": material_id}
    )
    if attachment_id:
        await connection.execute(
            text("delete from study.study_attachment where id = :id"), {"id": attachment_id}
        )


Kind = Literal["note", "session"]

__all__ = [
    "AttachmentOut",
    "Hit",
    "MaterialIn",
    "MaterialOut",
    "NotFound",
    "Note",
    "NoteBrief",
    "NoteEdit",
    "NoteIn",
    "Place",
]
