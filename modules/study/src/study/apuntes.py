from __future__ import annotations

import re
import unicodedata
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_tenancy import kernel_url, user_headers
from study import notes as local
from study.notes import Hit, Note, NoteBrief, NoteEdit, NoteIn
from study.studies import Conflict, NotFound, Source, _own

MODULE = "study"
ROOT = "Study"
FORBIDDEN = re.compile(r"[/\\:\[\]#^|]+")


class Unavailable(Exception):
    pass


async def ask(client: httpx.AsyncClient, service: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.post(
            f"{kernel_url()}/internal/capabilities/{service}",
            json=body,
            headers={**user_headers(), "x-arga-module": MODULE},
            timeout=30.0,
        )
    except httpx.HTTPError as error:
        raise Unavailable(f"los apuntes no contestan ({type(error).__name__})") from error
    detail = ""
    if response.status_code != 200:
        try:
            detail = str(response.json().get("detail") or "")
        except ValueError:
            detail = response.text[:200]
    if response.status_code == 404:
        raise NotFound(detail or "ese apunte")
    if response.status_code == 409:
        raise Conflict(detail)
    if response.status_code == 422:
        raise Conflict(detail)
    if response.status_code != 200:
        raise Unavailable(detail or f"los apuntes contestan {response.status_code}")
    return response.json()


def clean(name: str) -> str:
    return FORBIDDEN.sub("-", name).strip(" .-") or "Sin nombre"


COURSES = text("select id, name, tone, notes_folder from study.study_course order by created_at")
SUBJECTS = text("select id, course_id, name from study.study_subject")


class Places:
    def __init__(self, courses: list[Any], subjects: list[Any]) -> None:
        self.courses = {str(c.id): c for c in courses}
        self.subjects = {str(s.id): s for s in subjects}

    @classmethod
    async def load(cls, connection: AsyncConnection) -> Places:
        return cls(
            (await connection.execute(COURSES)).all(), (await connection.execute(SUBJECTS)).all()
        )

    def course_folder(self, course_id: str) -> str:
        course = self.courses[course_id]
        return (course.notes_folder or f"{ROOT}/{clean(course.name)}").strip("/")

    def subject_folder(self, subject_id: str) -> str:
        subject = self.subjects[subject_id]
        return f"{self.course_folder(str(subject.course_id))}/{clean(subject.name)}"

    def locate(self, folder: str) -> tuple[str | None, str | None]:
        key = folder.casefold()
        best: tuple[str | None, str | None] = (None, None)
        for course_id in self.courses:
            base = self.course_folder(course_id).casefold()
            if key == base or key.startswith(base + "/"):
                best = (course_id, None)
                for subject_id, subject in self.subjects.items():
                    if str(subject.course_id) != course_id:
                        continue
                    own = self.subject_folder(subject_id).casefold()
                    if key == own or key.startswith(own + "/"):
                        return course_id, subject_id
        return best


INDEX = text(
    "select n.id, n.notebook_id, n.course_id, n.subject_id, n.session_id, s.starts_at "
    "from study.study_note n left join study.study_session s on s.id = n.session_id "
    "where n.notebook_id = any(cast(:ids as uuid[]))"
)


async def _index(connection: AsyncConnection, ids: list[str]) -> dict[str, Any]:
    if not ids:
        return {}
    rows = (await connection.execute(INDEX, {"ids": ids})).all()
    return {str(row.notebook_id): row for row in rows}


def _brief(ref: dict[str, Any], places: Places, row: Any | None, course_id: str | None) -> dict:
    props = ref.get("properties") or {}
    located_course, located_subject = places.locate(ref["folder"])
    course = (
        str(row.course_id) if row else (props.get("study_estudio") or located_course or course_id)
    )
    subject = (
        str(row.subject_id)
        if row and row.subject_id
        else props.get("study_asignatura") or located_subject
    )
    session = str(row.session_id) if row and row.session_id else props.get("study_clase")
    if course not in places.courses:
        course = course_id
    if subject not in places.subjects:
        subject = None
    info = places.courses.get(course) if course else None
    folder = ""
    if course:
        base = places.course_folder(course)
        if ref["folder"].casefold().startswith(base.casefold() + "/"):
            folder = ref["folder"][len(base) + 1 :]
    return {
        "folder": folder,
        "id": ref["id"],
        "course_id": course or "",
        "subject_id": subject,
        "session_id": session,
        "title": ref["title"],
        "excerpt": ref["excerpt"],
        "course": info.name if info else "",
        "subject": places.subjects[subject].name if subject else None,
        "tone": info.tone if info else 1,
        "session_start": row.starts_at if row else None,
        "created_at": ref["created_at"],
        "updated_at": ref["updated_at"],
        "words": ref["words"],
    }


async def _briefs(
    connection: AsyncConnection, refs: list[dict], places: Places, course_id: str | None
) -> list[NoteBrief]:
    index = await _index(connection, [r["id"] for r in refs])
    return [NoteBrief(**_brief(r, places, index.get(r["id"]), course_id)) for r in refs]


async def _list(client: httpx.AsyncClient, **asked: Any) -> list[dict]:
    body = contracts.NotesList(**asked).model_dump(exclude_none=True)
    return (await ask(client, contracts.NOTES_LIST, body))["notes"]


async def notes(
    connection: AsyncConnection,
    client: httpx.AsyncClient,
    *,
    course_id: str | None = None,
    subject_id: str | None = None,
    session_id: str | None = None,
    limit: int = 200,
) -> list[NoteBrief]:
    places = await Places.load(connection)
    refs: dict[str, dict] = {}
    if session_id:
        for ref in await _list(client, property="study_clase", value=session_id, limit=limit):
            refs[ref["id"]] = ref
    elif subject_id:
        await _own(connection, "study_subject", subject_id)
        for ref in await _list(client, folder=places.subject_folder(subject_id), limit=limit):
            refs[ref["id"]] = ref
        for ref in await _list(client, property="study_asignatura", value=subject_id, limit=limit):
            refs[ref["id"]] = ref
    elif course_id:
        await _own(connection, "study_course", course_id)
        for ref in await _list(client, folder=places.course_folder(course_id), limit=limit):
            refs[ref["id"]] = ref
    else:
        for one in places.courses:
            for ref in await _list(client, folder=places.course_folder(one), limit=limit):
                refs[ref["id"]] = ref
    ordered = sorted(refs.values(), key=lambda r: r["updated_at"], reverse=True)[:limit]
    return await _briefs(connection, ordered, places, course_id)


async def note(connection: AsyncConnection, client: httpx.AsyncClient, note_id: str) -> Note:
    full = await ask(client, contracts.NOTES_READ, {"id": note_id})
    places = await Places.load(connection)
    index = await _index(connection, [note_id])
    brief = _brief(full, places, index.get(note_id), None)
    if not brief["course_id"]:
        raise NotFound("ese apunte no es de ningún estudio")
    return Note(**brief, body=full["body"])


async def _place(connection: AsyncConnection, item: NoteIn) -> tuple[str, str | None, Any]:
    course_id, subject_id, starts = item.course_id, item.subject_id, None
    if item.session_id:
        await _own(connection, "study_session", item.session_id)
        row = (
            await connection.execute(
                text(
                    "select course_id, subject_id, starts_at from study.study_session where id = :id"
                ),
                {"id": item.session_id},
            )
        ).one()
        course_id = str(row.course_id)
        subject_id = str(row.subject_id) if row.subject_id else None
        starts = row.starts_at
    await _own(connection, "study_course", course_id)
    await local._place_note(
        connection, item.model_copy(update={"subject_id": subject_id}), course_id
    )
    return course_id, subject_id, starts


def _title(item: NoteIn, starts: Any) -> str:
    if item.title.strip():
        return item.title.strip()
    if starts is not None:
        return f"Clase del {starts.date().isoformat()}"
    return "Apuntes"


async def add_note(
    connection: AsyncConnection, client: httpx.AsyncClient, item: NoteIn, source: Source = "app"
) -> Note:
    course_id, subject_id, starts = await _place(connection, item)
    places = await Places.load(connection)
    folder = places.subject_folder(subject_id) if subject_id else places.course_folder(course_id)
    properties: dict[str, Any] = {"study_estudio": course_id}
    if subject_id:
        properties["study_asignatura"] = subject_id
    if item.session_id:
        properties["study_clase"] = item.session_id
    created = await ask(
        client,
        contracts.NOTES_CREATE,
        {
            "folder": folder,
            "title": _title(item, starts),
            "body": item.body,
            "properties": properties,
        },
    )
    row_id = await connection.scalar(
        text(
            "insert into study.study_note "
            "(course_id, subject_id, session_id, title, source, notebook_id) "
            "values (:course, :subject, :session, :title, :source, :notebook) returning id"
        ),
        {
            "course": course_id,
            "subject": subject_id,
            "session": item.session_id,
            "title": created["title"][:200],
            "source": source,
            "notebook": created["id"],
        },
    )
    await local._claim_images(connection, str(row_id), item.body)
    return await note(connection, client, created["id"])


async def update_note(
    connection: AsyncConnection, client: httpx.AsyncClient, note_id: str, edit: NoteEdit
) -> Note:
    current = await note(connection, client, note_id)
    places = await Places.load(connection)
    folder = None
    if edit.subject_id and edit.subject_id != current.subject_id:
        await local._place_note(connection, edit, current.course_id)
        folder = places.subject_folder(edit.subject_id)
    title = edit.title.strip() or None
    await ask(
        client,
        contracts.NOTES_WRITE,
        {
            "id": note_id,
            "body": edit.body,
            **({"title": title} if title and title != current.title else {}),
            **({"folder": folder} if folder else {}),
        },
    )
    row_id = await connection.scalar(
        text(
            "update study.study_note set title = coalesce(:title, title), "
            "subject_id = coalesce(:subject, subject_id), updated_at = now() "
            "where notebook_id = :id returning id"
        ),
        {"title": title, "subject": edit.subject_id, "id": note_id},
    )
    if row_id is not None:
        await local._claim_images(connection, str(row_id), edit.body)
    return await note(connection, client, note_id)


async def delete_note(connection: AsyncConnection, client: httpx.AsyncClient, note_id: str) -> None:
    await note(connection, client, note_id)
    await ask(client, contracts.NOTES_TRASH, {"id": note_id})
    row_id = await connection.scalar(
        text("select id from study.study_note where notebook_id = :id"), {"id": note_id}
    )
    if row_id is not None:
        await local.delete_note(connection, str(row_id))


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def mark(fragment: str, query: str) -> str:
    wanted = [w for w in re.findall(r"[^\W_]+", _fold(query)) if w]
    stems = {
        w[: -len(e)]
        for w in wanted
        for e in ("es", "en", "s", "n", "e")
        if w.endswith(e) and len(w) - len(e) >= 4
    }
    prefixes = set(wanted) | stems

    def one(match: re.Match[str]) -> str:
        word = match.group(0)
        return f"«{word}»" if any(_fold(word).startswith(p) for p in prefixes) else word

    return re.sub(r"[^\W_]+", one, fragment)


async def find(
    connection: AsyncConnection, client: httpx.AsyncClient, query: str, *, limit: int = 30
) -> list[Hit]:
    places = await Places.load(connection)
    refs: list[dict] = []
    for one in places.courses:
        refs.extend(await _list(client, folder=places.course_folder(one), query=query, limit=limit))
    briefs = await _briefs(connection, refs[:limit], places, None)
    return [
        Hit(**brief.model_dump(), fragment=mark(ref["excerpt"], query), rank=float(len(refs) - i))
        for i, (brief, ref) in enumerate(zip(briefs, refs[:limit], strict=True))
    ]
