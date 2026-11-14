from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from notebook import markdown as md
from notebook import notes

AUTHOR = "app"


def plain(markdown: str) -> str:
    out = re.sub(r"^\s*(```|~~~).*?^\s*\1\s*$", " ", markdown, flags=re.MULTILINE | re.DOTALL)
    out = re.sub(r"^\s{0,3}#{1,6}\s.*$", " ", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*\|.*$", " ", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*([-*_])(\s*\1){2,}\s*$", " ", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*>\s*\[![^\]]*\][+-]?", " ", out, flags=re.MULTILINE)
    out = re.sub(r"^\s*>+", " ", out, flags=re.MULTILINE)
    out = re.sub(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)", " ", out)
    out = re.sub(
        r"\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]", lambda m: m.group(2) or m.group(1), out
    )
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", out)
    out = re.sub(r"^\s*(?:[-+*]|\d+\.)\s+(?:\[[ xX]\]\s*)?", " ", out, flags=re.MULTILINE)
    out = re.sub(r"\*\*|__|==|~~|[*`]|(?<!\w)_|_(?!\w)", "", out)
    out = re.sub(r"[#|]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return re.sub(r" ([.,;:!?)])", r"\1", out)


def without_title(body: str, title: str) -> str:
    stripped = body.lstrip("\n")
    first, _, rest = stripped.partition("\n")
    heading = first.lstrip("#").strip() if first.startswith("#") else None
    if heading is not None and md.key(heading) == md.key(title):
        return rest
    return body


def _ref(row: Any, query: str | None = None) -> dict[str, Any]:
    body = md.split(row.content).body
    text_ = plain(without_title(body, row.title))
    return {
        "id": str(row.id),
        "folder": row.folder,
        "title": row.title,
        "path": md.path_of(row.folder, row.title),
        "properties": row.properties,
        "excerpt": md.snippet(text_, query) if query else text_[:180],
        "words": len(text_.split()),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
    }


def _full(note: notes.Note) -> dict[str, Any]:
    ref = _ref(note)
    return contracts.note_full(**ref, body=md.split(note.content).body, version=note.version)


COLUMNS = "id, folder, title, content, properties, created_at, updated_at, updated_by"


async def listed(connection: AsyncConnection, asked: contracts.NotesList) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": asked.limit}
    where = [
        "deleted_at is null",
        "not exists (select 1 from notebook.notebook_record r where r.note_id = notebook_note.id "
        "and r.day is null and not r.removed)",
    ]
    if asked.folder:
        params["folder"] = md.key(md.folder(asked.folder))
        where.append(
            "(folder_key = :folder or left(folder_key, length(:folder) + 1) = :folder || '/')"
        )
    if asked.property:
        params["name"] = asked.property
        if asked.value is None:
            where.append("properties ? :name")
        else:
            params["value"] = (
                str(asked.value).lower() if isinstance(asked.value, bool) else str(asked.value)
            )
            where.append(
                "(properties ->> :name = :value or (jsonb_typeof(properties -> :name) = 'array' "
                "and properties -> :name ? :value))"
            )
    words = md.query_words(asked.query or "")
    order = "updated_at desc"
    if words:
        params["q"] = md.tsquery(asked.query or "")
        where.append("search @@ to_tsquery('simple', :q)")
        order = "ts_rank(search, to_tsquery('simple', :q)) desc, updated_at desc"
    rows = (
        await connection.execute(
            text(
                f"select {COLUMNS} from notebook.notebook_note where {' and '.join(where)} "
                f"order by {order} limit :limit"
            ),
            params,
        )
    ).all()
    return contracts.notes_found(notes=[_ref(row, asked.query) for row in rows])


async def read(connection: AsyncConnection, asked: contracts.NotesRead) -> dict[str, Any]:
    return _full(await notes.get(connection, asked.id))


async def create(connection: AsyncConnection, asked: contracts.NotesCreate) -> dict[str, Any]:
    content = md.with_properties(asked.body, dict(asked.properties))
    title = asked.title
    for attempt in range(2, 100):
        try:
            return _full(await notes.create(connection, asked.folder, title, content, AUTHOR))
        except notes.Conflict:
            title = f"{asked.title} ({attempt})"
    raise notes.Conflict(f"there is no free title for '{asked.title}'")


async def write(connection: AsyncConnection, asked: contracts.NotesWrite) -> dict[str, Any]:
    current = await notes.get(connection, asked.id)
    if asked.version is not None and asked.version != current.version:
        raise notes.Conflict(
            "the note changed while you were editing it "
            f"(version {current.version}, not {asked.version})"
        )
    if asked.body is not None:
        head = current.content[: len(current.content) - len(md.split(current.content).body)]
        current = await notes.write(connection, current.id, head + asked.body, None, AUTHOR)
    if asked.title is not None or asked.folder is not None:
        current, _ = await notes.move(connection, current.id, asked.folder, asked.title, AUTHOR)
    return _full(current)


async def trash(connection: AsyncConnection, asked: contracts.NotesTrash) -> dict[str, Any]:
    await notes.trash(connection, asked.id)
    return {"trashed": asked.id}


SERVICES = {
    contracts.NOTES_LIST: (contracts.NotesList, listed),
    contracts.NOTES_READ: (contracts.NotesRead, read),
    contracts.NOTES_CREATE: (contracts.NotesCreate, create),
    contracts.NOTES_WRITE: (contracts.NotesWrite, write),
    contracts.NOTES_TRASH: (contracts.NotesTrash, trash),
}
