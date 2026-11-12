from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from notebook import fichas, mentions
from notebook import markdown as md

MADRID = ZoneInfo("Europe/Madrid")

Author = Literal["app", "tool", "import"]

APP_REVISION_EVERY = timedelta(minutes=10)
MAX_CONTENT = 1_000_000


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Invalid(Exception):
    pass


def today() -> date:
    return datetime.now(MADRID).date()


class NoteSummary(BaseModel):
    id: str
    folder: str
    title: str
    path: str
    updated_at: datetime
    updated_by: Author
    updated_app: str | None = None


class Note(NoteSummary):
    content: str
    properties: dict[str, Any]
    tags: list[str]
    outline: list[dict[str, Any]]
    version: int
    created_at: datetime


class LinkOut(BaseModel):
    target: str
    kind: str
    heading: str | None
    alias: str | None
    embed: bool
    line: int
    note: NoteSummary | None


class Backlink(BaseModel):
    note: NoteSummary
    lines: list[str]


class Revision(BaseModel):
    id: str
    title: str
    folder: str
    written_by: Author
    written_at: datetime
    replaced_by: Author
    replaced_at: datetime
    written_app: str | None = None
    replaced_app: str | None = None


class RevisionFull(Revision):
    content: str


class Trashed(NoteSummary):
    deleted_at: datetime


@dataclass(frozen=True)
class _Row:
    id: str
    folder: str
    folder_key: str
    title: str
    title_key: str
    content: str
    properties: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime
    updated_by: Author
    updated_app: str | None = None


COLUMNS = (
    "id, folder, folder_key, title, title_key, content, properties, version, created_at, "
    "updated_at, updated_by, updated_app"
)


def _row(found: Any) -> _Row:
    return _Row(
        id=str(found.id),
        folder=found.folder,
        folder_key=found.folder_key,
        title=found.title,
        title_key=found.title_key,
        content=found.content,
        properties=found.properties,
        version=found.version,
        created_at=found.created_at,
        updated_at=found.updated_at,
        updated_by=found.updated_by,
        updated_app=found.updated_app,
    )


def _summary(row: Any) -> NoteSummary:
    return NoteSummary(
        id=str(row.id),
        folder=row.folder,
        title=row.title,
        path=md.path_of(row.folder, row.title),
        updated_at=row.updated_at,
        updated_by=row.updated_by,
        updated_app=getattr(row, "updated_app", None),
    )


def _note(row: _Row) -> Note:
    return Note(
        **_summary(row).model_dump(),
        content=row.content,
        properties=row.properties,
        tags=md.tags(row.content),
        outline=md.outline(row.content),
        version=row.version,
        created_at=row.created_at,
    )


async def _by_id(connection: AsyncConnection, note_id: str) -> _Row:
    try:
        UUID(note_id)
    except ValueError as error:
        raise NotFound(f"la nota {note_id}") from error
    found = (
        await connection.execute(
            text(
                f"select {COLUMNS} from notebook.notebook_note where id = :id and deleted_at is null"
            ),
            {"id": note_id},
        )
    ).first()
    if found is None:
        raise NotFound(f"la nota {note_id}")
    return _row(found)


async def get(connection: AsyncConnection, note_id: str) -> Note:
    return _note(await _by_id(connection, note_id))


async def find_row(connection: AsyncConnection, ref: str) -> _Row:
    clean = ref.strip()
    if clean.startswith("[[") and clean.endswith("]]"):
        clean = clean[2:-2].split("|")[0].split("#")[0]
    try:
        UUID(clean)
    except ValueError:
        pass
    else:
        return await _by_id(connection, clean)
    clean = md.nfc(clean).strip().strip("/")
    if clean.lower().endswith(".md"):
        clean = clean[:-3]
    folder_key: str | None = None
    name = clean
    if "/" in clean:
        folder_part, name = clean.rsplit("/", 1)
        folder_key = md.key(md.folder(folder_part))
    rows = (
        await connection.execute(
            text(
                f"select {COLUMNS} from notebook.notebook_note "
                "where deleted_at is null and title_key = :title "
                "  and (cast(:folder as text) is null or folder_key = :folder "
                "       or right(folder_key, length(:folder) + 1) = '/' || :folder) "
                "order by length(folder_key), folder_key"
            ),
            {"title": md.key(name), "folder": folder_key},
        )
    ).all()
    if not rows:
        similar = (
            await connection.execute(
                text(
                    "select folder, title from notebook.notebook_note "
                    "where deleted_at is null and position(:part in lower(title)) > 0 "
                    "order by length(title) limit 5"
                ),
                {"part": md.nfc(name).lower()[:60]},
            )
        ).all()
        hint = ""
        if similar:
            hint = ". Parecidas: " + ", ".join(
                f"«{md.path_of(r.folder, r.title)}»" for r in similar
            )
        raise NotFound(f"la nota «{ref}»{hint}")
    exact = [r for r in rows if folder_key is None or r.folder_key == folder_key]
    if folder_key is not None and len(exact) == 1:
        return _row(exact[0])
    if len(rows) > 1:
        paths = ", ".join(f"«{md.path_of(r.folder, r.title)}»" for r in rows[:10])
        raise Conflict(f"hay {len(rows)} notas «{name}»: {paths}. Di cuál con su ruta")
    return _row(rows[0])


async def find(connection: AsyncConnection, ref: str) -> Note:
    return _note(await find_row(connection, ref))


def _folder(value: str | None) -> str:
    try:
        return md.folder(value)
    except md.InvalidName as error:
        raise Invalid(str(error)) from error


def _title(value: str) -> str:
    try:
        return md.title(value)
    except md.InvalidName as error:
        raise Invalid(str(error)) from error


async def ensure_folder(connection: AsyncConnection, path: str) -> None:
    for each in md.ancestors(path):
        await connection.execute(
            text(
                "insert into notebook.notebook_folder (path, path_key) values (:path, :key) "
                "on conflict (user_id, path_key) do nothing"
            ),
            {"path": each, "key": md.key(each)},
        )


async def _folder_path(connection: AsyncConnection, path: str) -> str:
    if not path:
        return ""
    parts = path.split("/")
    found: list[str] = []
    for i in range(len(parts)):
        prefix = "/".join(found + parts[i : i + 1])
        stored = await connection.scalar(
            text("select path from notebook.notebook_folder where path_key = :key"),
            {"key": md.key(prefix)},
        )
        found.append(stored.rsplit("/", 1)[-1] if stored else parts[i])
    return "/".join(found)


async def _snapshot(
    connection: AsyncConnection, current: _Row, author: Author, app: str | None = None
) -> None:
    throttled = (author == "app" and current.updated_by == "app") or (
        author == "import" and app is not None and current.updated_app == app
    )
    if throttled:
        recent = await connection.scalar(
            text(
                "select 1 from notebook.notebook_revision "
                "where note_id = :id and replaced_by = :author "
                "  and replaced_app is not distinct from :app "
                "  and replaced_at > now() - cast(:every as interval) "
                "limit 1"
            ),
            {"id": current.id, "author": author, "app": app, "every": APP_REVISION_EVERY},
        )
        if recent:
            return
    await connection.execute(
        text(
            "insert into notebook.notebook_revision "
            "(note_id, folder, title, content, written_by, written_at, replaced_by, "
            "written_app, replaced_app) "
            "values (:id, :folder, :title, :content, :written_by, :written_at, :replaced_by, "
            ":written_app, :replaced_app)"
        ),
        {
            "id": current.id,
            "folder": current.folder,
            "title": current.title,
            "content": current.content,
            "written_by": current.updated_by,
            "written_at": current.updated_at,
            "replaced_by": author,
            "written_app": current.updated_app,
            "replaced_app": app,
        },
    )


async def _derive(connection: AsyncConnection, note_id: str, content: str) -> None:
    await connection.execute(
        text("delete from notebook.notebook_link where note_id = :id"), {"id": note_id}
    )
    await connection.execute(
        text("delete from notebook.notebook_tag where note_id = :id"), {"id": note_id}
    )
    found = md.links(content)
    if found:
        await connection.execute(
            text(
                "insert into notebook.notebook_link (note_id, position, line, kind, target, title_key, "
                "folder_key, heading, alias, embed) values (:id, :position, :line, :kind, "
                ":target, :title_key, :folder_key, :heading, :alias, :embed)"
            ),
            [
                {
                    "id": note_id,
                    "position": position,
                    "line": link.line,
                    "kind": link.kind,
                    "target": link.target[:1000],
                    "title_key": link.title_key[:1000],
                    "folder_key": link.folder_key,
                    "heading": link.heading,
                    "alias": link.alias,
                    "embed": link.embed,
                }
                for position, link in enumerate(found)
            ],
        )
    tags = md.tags(content)
    if tags:
        await connection.execute(
            text("insert into notebook.notebook_tag (note_id, tag) values (:id, :tag)"),
            [{"id": note_id, "tag": tag} for tag in tags],
        )


async def _publish(connection: AsyncConnection, note_id: str, dedup: str, **payload: Any) -> None:
    await connection.execute(
        text(
            "insert into notebook.notebook_outbox (type, payload, dedup_hash) "
            "values ('notebook.note_changed', cast(:payload as jsonb), :dedup) "
            "on conflict (user_id, dedup_hash) do nothing"
        ),
        {"payload": json.dumps({"note_id": note_id, **payload}), "dedup": dedup},
    )


def _check_content(content: str) -> str:
    content = content.replace("\x00", "")
    if len(content) > MAX_CONTENT:
        raise Invalid(f"la nota pasa de {MAX_CONTENT:,} caracteres".replace(",", "."))
    return content


async def _taken(connection: AsyncConnection, folder: str, title: str, but: str | None) -> bool:
    return bool(
        await connection.scalar(
            text(
                "select 1 from notebook.notebook_note where deleted_at is null and folder_key = :folder "
                "and title_key = :title "
                "and (cast(:but as uuid) is null or id <> cast(:but as uuid))"
            ),
            {"folder": md.key(folder), "title": md.key(title), "but": but},
        )
    )


def _taken_message(folder: str, title: str) -> str:
    where = f"en «{folder}»" if folder else "en la raíz"
    return f"ya hay una nota «{title}» {where}"


async def create(
    connection: AsyncConnection,
    folder: str | None,
    title: str,
    content: str = "",
    author: Author = "app",
    app: str | None = None,
) -> Note:
    clean_folder = await _folder_path(connection, _folder(folder))
    clean_title = _title(title)
    content = md.nfc(_check_content(content))
    if await _taken(connection, clean_folder, clean_title, None):
        raise Conflict(_taken_message(clean_folder, clean_title))
    await ensure_folder(connection, clean_folder)
    try:
        created = (
            await connection.execute(
                text(
                    "insert into notebook.notebook_note (folder, folder_key, title, title_key, content, "
                    "properties, search_text, updated_by, updated_app) values (:folder, "
                    ":folder_key, :title, :title_key, :content, cast(:properties as jsonb), "
                    f":search, :author, :app) returning {COLUMNS}"
                ),
                {
                    "folder": clean_folder,
                    "folder_key": md.key(clean_folder),
                    "title": clean_title,
                    "title_key": md.key(clean_title),
                    "content": content,
                    "properties": json.dumps(md.properties(content)),
                    "search": md.search_text(clean_title, content),
                    "author": author,
                    "app": app if author == "import" else None,
                },
            )
        ).one()
    except IntegrityError as error:
        raise Conflict(_taken_message(clean_folder, clean_title)) from error
    row = _row(created)
    await _derive(connection, row.id, content)
    await mentions.sync(connection, row.id)
    await _publish(connection, row.id, f"note:{row.id}:1", by=author, created=True)
    return _note(row)


async def _save(
    connection: AsyncConnection,
    current: _Row,
    content: str,
    author: Author,
    folder: str | None = None,
    title: str | None = None,
    app: str | None = None,
) -> _Row:
    content = md.nfc(_check_content(content))
    folder = current.folder if folder is None else folder
    title = current.title if title is None else title
    if content == current.content and folder == current.folder and title == current.title:
        return current
    app = app if author == "import" else None
    await _snapshot(connection, current, author, app)
    try:
        saved = (
            await connection.execute(
                text(
                    "update notebook.notebook_note set folder = :folder, folder_key = :folder_key, "
                    "title = :title, title_key = :title_key, content = :content, "
                    "properties = cast(:properties as jsonb), search_text = :search, "
                    "version = version + 1, updated_at = now(), updated_by = :author, "
                    f"updated_app = :app where id = :id returning {COLUMNS}"
                ),
                {
                    "id": current.id,
                    "app": app,
                    "folder": folder,
                    "folder_key": md.key(folder),
                    "title": title,
                    "title_key": md.key(title),
                    "content": content,
                    "properties": json.dumps(md.properties(content)),
                    "search": md.search_text(title, content),
                    "author": author,
                },
            )
        ).one()
    except IntegrityError as error:
        raise Conflict(_taken_message(folder, title)) from error
    row = _row(saved)
    if content != current.content:
        await _derive(connection, row.id, content)
    await mentions.sync(connection, row.id)
    await _publish(connection, row.id, f"note:{row.id}:{row.version}", by=author)
    return row


async def write(
    connection: AsyncConnection, note_id: str, content: str, version: int | None, author: Author
) -> Note:
    current = await _by_id(connection, note_id)
    if version is not None and version != current.version:
        raise Conflict(
            f"la nota cambió mientras la editabas (versión {current.version}, no {version})"
        )
    theirs = await owned(connection, current.id)
    if theirs is not None:
        content = fichas.compose(content, theirs)
    return _note(await _save(connection, current, content, author))


async def edit(connection: AsyncConnection, ref: str, change, author: Author) -> tuple[Note, Note]:
    current = await find_row(connection, ref)
    try:
        content = change(current.content)
    except (md.NotFoundInNote, md.InvalidProperties) as error:
        raise Invalid(str(error)) from error
    except md.Ambiguous as error:
        raise Conflict(str(error)) from error
    if author != "import":
        theirs = await owned(connection, current.id)
        if theirs is not None and touches(theirs, current.content, content):
            raise Invalid(
                f"lo de arga en esta nota (el bloque entre «{md.BLOCK_START}» y «{md.BLOCK_END}» "
                f"y las propiedades {', '.join(sorted(theirs.properties))}) lo escribe "
                f"{theirs.names}: se cambia allí y aquí se rehace solo. Lo que escribas fuera del "
                "bloque es tuyo"
            )
    saved = await _save(connection, current, content, author)
    return _note(current), _note(saved)


OWNED = text("""
    select app, app_name, record_id, title, kind, href, day, properties, body
    from notebook.notebook_record
    where note_id = :id and not removed
""")


def ficha(row: Any) -> fichas.Ficha:
    return fichas.Ficha(
        app=row.app,
        app_name=row.app_name,
        record_id=row.record_id,
        title=row.title,
        kind=row.kind,
        href=row.href,
        day=row.day,
        properties=row.properties,
        body=row.body,
    )


async def owned(connection: AsyncConnection, note_id: str) -> fichas.Owned | None:
    rows = (await connection.execute(OWNED, {"id": note_id})).all()
    return fichas.owned([ficha(row) for row in rows])


_ABSENT = object()


def touches(theirs: fichas.Owned, before: str, after: str) -> bool:
    old, new = md.block(before), md.block(after)
    if (old is None) != (new is None) or (old and new and old.inner != new.inner):
        return True
    old_values, new_values = md.properties(before), md.properties(after)
    return any(
        old_values.get(name, _ABSENT) != new_values.get(name, _ABSENT) for name in theirs.properties
    )


class Owner(BaseModel):
    apps: list[dict[str, str]]
    properties: list[str]
    day: bool


async def owner(connection: AsyncConnection, note_id: str) -> Owner | None:
    theirs = await owned(connection, note_id)
    if theirs is None:
        return None
    seen: dict[str, dict[str, str]] = {}
    for one in theirs.apps:
        seen.setdefault(
            one.app, {"app": one.app, "name": one.app_name, "href": one.href, "kind": one.kind}
        )
    return Owner(
        apps=list(seen.values()),
        properties=list(theirs.properties),
        day=any(one.day is not None for one in theirs.apps),
    )


class ImportNote(BaseModel):
    folder: str = ""
    title: str
    content: str = ""


class Refused(BaseModel):
    path: str
    reason: str


class Imported(BaseModel):
    created: int
    filled: int = 0
    skipped: list[str]
    invalid: list[Refused]


async def import_notes(connection: AsyncConnection, items: list[ImportNote]) -> Imported:
    created = 0
    filled = 0
    skipped: list[str] = []
    invalid: list[Refused] = []
    for item in items:
        path = md.path_of(item.folder, item.title)
        try:
            folder = await _folder_path(connection, _folder(item.folder))
            title = _title(item.title)
            if await _taken(connection, folder, title, None):
                existing = (
                    await connection.execute(
                        text(
                            f"select {COLUMNS} from notebook.notebook_note where deleted_at is null "
                            "and folder_key = :folder and title_key = :title"
                        ),
                        {"folder": md.key(folder), "title": md.key(title)},
                    )
                ).one()
                content = item.content.replace("\x00", "")
                if not existing.content.strip() and content.strip():
                    await _save(connection, _row(existing), content, "import")
                    filled += 1
                else:
                    skipped.append(md.path_of(folder, title))
                continue
            await create(connection, folder, title, item.content, "import")
            created += 1
        except (Invalid, Conflict) as error:
            invalid.append(Refused(path=path, reason=str(error)))
    return Imported(created=created, filled=filled, skipped=skipped, invalid=invalid)


async def _incoming(
    connection: AsyncConnection, targets: dict[str, str]
) -> dict[str, dict[int, str]]:
    if not targets:
        return {}
    rows = (
        await connection.execute(
            text(
                "select l.note_id, l.position, "
                "  notebook.resolve(l.title_key, l.folder_key, s.folder_key) as target "
                "from notebook.notebook_link l "
                "join notebook.notebook_note s on s.id = l.note_id and s.deleted_at is null "
                "where l.kind = 'note' and l.title_key = any(:keys)"
            ),
            {"keys": list(set(targets.values()))},
        )
    ).all()
    found: dict[str, dict[int, str]] = {}
    for row in rows:
        if row.target is not None and str(row.target) in targets:
            found.setdefault(str(row.note_id), {})[row.position] = str(row.target)
    return found


async def _relink(
    connection: AsyncConnection,
    incoming: dict[str, dict[int, str]],
    author: Author,
    app: str | None = None,
) -> int:
    changed = 0
    for source_id, positions in incoming.items():
        try:
            source = await _by_id(connection, source_id)
        except NotFound:
            continue
        found = md.links(source.content)
        replacements: dict[int, str] = {}
        for position, target_id in positions.items():
            if position >= len(found):
                continue
            link = found[position]
            now = await connection.scalar(
                text("select notebook.resolve(:title, :folder, :from)"),
                {"title": link.title_key, "folder": link.folder_key, "from": source.folder_key},
            )
            if now is not None and str(now) == target_id:
                continue
            target = await _by_id(connection, target_id)
            by_title = await connection.scalar(
                text("select notebook.resolve(:title, null, :from)"),
                {"title": target.title_key, "from": source.folder_key},
            )
            replacements[link.start] = (
                target.title
                if by_title is not None and str(by_title) == target_id
                else md.path_of(target.folder, target.title)
            )
        if replacements:
            content = md.rewrite_links(
                source.content, lambda link, found=replacements: found.get(link.start)
            )
            await _save(connection, source, content, author, app=app)
            changed += 1
    return changed


async def move(
    connection: AsyncConnection,
    ref: str,
    folder: str | None,
    title: str | None,
    author: Author,
    app: str | None = None,
) -> tuple[Note, int]:
    current = await find_row(connection, ref)
    new_folder = (
        current.folder if folder is None else await _folder_path(connection, _folder(folder))
    )
    new_title = current.title if title is None else _title(title)
    if new_folder == current.folder and new_title == current.title:
        return _note(current), 0
    if await _taken(connection, new_folder, new_title, current.id):
        raise Conflict(_taken_message(new_folder, new_title))
    incoming = await _incoming(connection, {current.id: current.title_key})
    await ensure_folder(connection, new_folder)
    moved = await _save(
        connection, current, current.content, author, new_folder, new_title, app=app
    )
    relinked = await _relink(connection, incoming, author, app)
    return _note(await _by_id(connection, moved.id)), relinked


async def create_folder(connection: AsyncConnection, path: str) -> str:
    clean = _folder(path)
    if not clean:
        raise Invalid("la carpeta no tiene nombre")
    clean = await _folder_path(connection, clean)
    await ensure_folder(connection, clean)
    return clean


async def move_folder(connection: AsyncConnection, old: str, new: str, author: Author) -> int:
    old_path = _folder(old)
    new_path = _folder(new)
    if not old_path or not new_path:
        raise Invalid("la raíz no se mueve")
    old_key, new_key = md.key(old_path), md.key(new_path)
    exists = await connection.scalar(
        text("select 1 from notebook.notebook_folder where path_key = :key"), {"key": old_key}
    )
    if not exists:
        raise NotFound(f"la carpeta «{old}»")
    if new_key == old_key and new_path == old_path:
        return 0
    if new_key.startswith(old_key + "/"):
        raise Invalid("una carpeta no se mueve dentro de sí misma")
    if new_key != old_key:
        taken = await connection.scalar(
            text("select 1 from notebook.notebook_folder where path_key = :key"), {"key": new_key}
        )
        if taken:
            raise Conflict(f"ya hay una carpeta «{new_path}»")
    under = "(path_key = :old_key or left(path_key, length(:old_key) + 1) = :old_key || '/')"
    notes_under = (
        "(folder_key = :old_key or left(folder_key, length(:old_key) + 1) = :old_key || '/')"
    )
    moving = (
        await connection.execute(
            text(
                "select id, title_key from notebook.notebook_note "
                f"where deleted_at is null and {notes_under}"
            ),
            {"old_key": old_key},
        )
    ).all()
    incoming = await _incoming(connection, {str(r.id): r.title_key for r in moving})
    params = {"old_key": old_key, "old": old_path, "new": new_path, "new_key": new_key}
    await connection.execute(
        text(
            "update notebook.notebook_folder set "
            "path = :new || substr(path, length(:old) + 1), "
            f"path_key = :new_key || substr(path_key, length(:old_key) + 1) where {under}"
        ),
        params,
    )
    await ensure_folder(connection, new_path)
    await connection.execute(
        text(
            "update notebook.notebook_note set "
            "folder = :new || substr(folder, length(:old) + 1), "
            "folder_key = :new_key || substr(folder_key, length(:old_key) + 1), "
            f"version = version + 1 where {notes_under}"
        ),
        params,
    )
    await _relink(connection, incoming, author)
    return len(moving)


async def delete_folder(connection: AsyncConnection, path: str) -> int:
    clean = _folder(path)
    if not clean:
        raise Invalid("la raíz no se borra")
    key = md.key(clean)
    exists = await connection.scalar(
        text("select 1 from notebook.notebook_folder where path_key = :key"), {"key": key}
    )
    if not exists:
        raise NotFound(f"la carpeta «{path}»")
    trashed = (
        await connection.execute(
            text(
                "update notebook.notebook_note set deleted_at = now() where deleted_at is null and "
                "(folder_key = :key or left(folder_key, length(:key) + 1) = :key || '/') "
                "returning id"
            ),
            {"key": key},
        )
    ).all()
    for row in trashed:
        await mentions.sync(connection, str(row.id), gone=True)
        await _publish(
            connection, str(row.id), f"trash:{row.id}:{datetime.now().isoformat()}", trashed=True
        )
    await connection.execute(
        text(
            "delete from notebook.notebook_folder where "
            "path_key = :key or left(path_key, length(:key) + 1) = :key || '/'"
        ),
        {"key": key},
    )
    return len(trashed)


async def trash(connection: AsyncConnection, note_id: str) -> None:
    current = await _by_id(connection, note_id)
    await connection.execute(
        text("update notebook.notebook_note set deleted_at = now() where id = :id"),
        {"id": current.id},
    )
    await mentions.sync(connection, current.id, gone=True)
    await _publish(connection, current.id, f"trash:{current.id}:{current.version}", trashed=True)


async def trashed(connection: AsyncConnection) -> list[Trashed]:
    rows = (
        await connection.execute(
            text(
                "select id, folder, title, updated_at, updated_by, deleted_at "
                "from notebook.notebook_note "
                "where deleted_at is not null order by deleted_at desc"
            )
        )
    ).all()
    return [Trashed(**_summary(r).model_dump(), deleted_at=r.deleted_at) for r in rows]


async def restore(connection: AsyncConnection, note_id: str) -> Note:
    found = (
        await connection.execute(
            text(
                f"select {COLUMNS} from notebook.notebook_note where id = :id and deleted_at is not null"
            ),
            {"id": note_id},
        )
    ).first()
    if found is None:
        raise NotFound(f"la nota {note_id} en la papelera")
    row = _row(found)
    if await _taken(connection, row.folder, row.title, row.id):
        raise Conflict(
            _taken_message(row.folder, row.title) + "; cambia el nombre de una de las dos"
        )
    await ensure_folder(connection, row.folder)
    await connection.execute(
        text("update notebook.notebook_note set deleted_at = null where id = :id"), {"id": row.id}
    )
    await mentions.sync(connection, row.id)
    await _publish(
        connection, row.id, f"restore:{row.id}:{datetime.now().isoformat()}", restored=True
    )
    return _note(row)


async def empty_trash(connection: AsyncConnection, note_id: str | None = None) -> int:
    rows = (
        await connection.execute(
            text(
                "delete from notebook.notebook_note where deleted_at is not null "
                "and (cast(:id as uuid) is null or id = cast(:id as uuid)) returning id"
            ),
            {"id": note_id},
        )
    ).all()
    return len(rows)


async def revisions(connection: AsyncConnection, note_id: str) -> list[Revision]:
    await _by_id(connection, note_id)
    rows = (
        await connection.execute(
            text(
                "select id, title, folder, written_by, written_at, replaced_by, replaced_at, "
                "written_app, replaced_app "
                "from notebook.notebook_revision where note_id = :id order by replaced_at desc"
            ),
            {"id": note_id},
        )
    ).all()
    return [Revision(**{**r._asdict(), "id": str(r.id)}) for r in rows]


async def revision(connection: AsyncConnection, note_id: str, revision_id: str) -> RevisionFull:
    found = (
        await connection.execute(
            text(
                "select id, title, folder, content, written_by, written_at, replaced_by, "
                "replaced_at, written_app, replaced_app "
                "from notebook.notebook_revision where id = :rid and note_id = :id"
            ),
            {"rid": revision_id, "id": note_id},
        )
    ).first()
    if found is None:
        raise NotFound(f"la versión {revision_id}")
    return RevisionFull(**{**found._asdict(), "id": str(found.id)})


async def restore_revision(
    connection: AsyncConnection, note_id: str, revision_id: str, author: Author
) -> Note:
    old = await revision(connection, note_id, revision_id)
    current = await _by_id(connection, note_id)
    wanted = old.content
    theirs = await owned(connection, current.id)
    if theirs is not None:
        wanted = fichas.compose(wanted, theirs)
    if current.content == wanted:
        return _note(current)
    await connection.execute(
        text(
            "insert into notebook.notebook_revision "
            "(note_id, folder, title, content, written_by, written_at, replaced_by, written_app) "
            "values (:id, :folder, :title, :content, :written_by, :written_at, :replaced_by, "
            ":written_app)"
        ),
        {
            "id": current.id,
            "folder": current.folder,
            "title": current.title,
            "content": current.content,
            "written_by": current.updated_by,
            "written_at": current.updated_at,
            "replaced_by": author,
            "written_app": current.updated_app,
        },
    )
    saved = (
        await connection.execute(
            text(
                "update notebook.notebook_note set content = :content, "
                "properties = cast(:properties as jsonb), search_text = :search, "
                "version = version + 1, updated_at = now(), updated_by = :author, "
                f"updated_app = null where id = :id returning {COLUMNS}"
            ),
            {
                "id": current.id,
                "content": wanted,
                "properties": json.dumps(md.properties(wanted)),
                "search": md.search_text(current.title, wanted),
                "author": author,
            },
        )
    ).one()
    row = _row(saved)
    await _derive(connection, row.id, row.content)
    await mentions.sync(connection, row.id)
    await _publish(connection, row.id, f"note:{row.id}:{row.version}", by=author)
    return _note(row)


FICHA_OF = (
    "select r.note_id from notebook.notebook_record r where r.link_key = :key and r.day is null "
    "and not r.removed limit 1"
)
FICHA_OF_LINK = (
    "select r.note_id from notebook.notebook_record r where r.link_key = l.title_key "
    "and r.day is null and not r.removed limit 1"
)


async def links_of(connection: AsyncConnection, note_id: str) -> list[LinkOut]:
    note = await _by_id(connection, note_id)
    rows = (
        await connection.execute(
            text(
                "select l.target, l.kind, l.heading, l.alias, l.embed, l.line, "
                "  t.id, t.folder, t.title, t.updated_at, t.updated_by, t.updated_app "
                "from notebook.notebook_link l "
                "left join notebook.notebook_note t on t.deleted_at is null and ("
                "  (l.kind = 'note' and t.id = notebook.resolve(l.title_key, l.folder_key, :from)) "
                f"  or (l.kind = 'app' and t.id = ({FICHA_OF_LINK})))"
                "where l.note_id = :id order by l.position"
            ),
            {"id": note.id, "from": note.folder_key},
        )
    ).all()
    return [
        LinkOut(
            target=r.target,
            kind=r.kind,
            heading=r.heading,
            alias=r.alias,
            embed=r.embed,
            line=r.line,
            note=_summary(r) if r.id else None,
        )
        for r in rows
    ]


async def backlinks(connection: AsyncConnection, note_id: str) -> list[Backlink]:
    note = await _by_id(connection, note_id)
    rows = (
        await connection.execute(
            text(
                "select s.id, s.folder, s.title, s.updated_at, s.updated_by, s.updated_app, "
                "  s.content, l.line "
                "from notebook.notebook_link l "
                "join notebook.notebook_note s on s.id = l.note_id and s.deleted_at is null "
                "where s.id <> :id and ("
                "  (l.kind = 'note' and l.title_key = :title "
                "   and notebook.resolve(l.title_key, l.folder_key, s.folder_key) = :id) "
                "  or (l.kind = 'app' and l.title_key in (select r.link_key "
                "      from notebook.notebook_record r where r.note_id = :id and r.day is null "
                "      and not r.removed))) "
                "order by s.title, s.folder, l.position"
            ),
            {"title": note.title_key, "id": note.id},
        )
    ).all()
    grouped: dict[str, Backlink] = {}
    for r in rows:
        entry = grouped.setdefault(str(r.id), Backlink(note=_summary(r), lines=[]))
        context = md.line(r.content, r.line)
        if context not in entry.lines:
            entry.lines.append(context)
    return list(grouped.values())


async def link_target(
    connection: AsyncConnection, target: str, from_note: str | None
) -> NoteSummary | None:
    kind, title_key, folder_key = md._target_parts(md.nfc(target).strip())
    if kind == "app":
        found = (
            await connection.execute(
                text(
                    "select id, folder, title, updated_at, updated_by, updated_app "
                    f"from notebook.notebook_note t where t.deleted_at is null and t.id = ({FICHA_OF})"
                ),
                {"key": title_key},
            )
        ).first()
        return _summary(found) if found else None
    if kind != "note":
        return None
    from_folder = ""
    if from_note:
        from_folder = (await _by_id(connection, from_note)).folder_key
    found = (
        await connection.execute(
            text(
                "select id, folder, title, updated_at, updated_by, updated_app "
                "from notebook.notebook_note where id = notebook.resolve(:title, :folder, :from)"
            ),
            {"title": title_key, "folder": folder_key, "from": from_folder},
        )
    ).first()
    return _summary(found) if found else None


Op = Literal["eq", "ne", "lt", "lte", "gt", "gte", "exists", "missing"]
SQL_OPS = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}


class PropertyFilter(BaseModel):
    name: str
    op: Op = "eq"
    value: str | float | int | bool | None = None


class Source(BaseModel):
    app: str
    name: str
    href: str


class Hit(NoteSummary):
    snippet: str
    tags: list[str]
    href: str
    source: Source | None = None
    changes: int | None = None


def _property_sql(i: int, one: PropertyFilter, params: dict[str, Any]) -> str:
    name = f"pn{i}"
    params[name] = one.name
    value = one.value
    if isinstance(value, str) and value.strip().lower() in ("today", "hoy"):
        value = today().isoformat()
    if one.op == "exists":
        return f"n.properties ? :{name}"
    if one.op == "missing":
        return f"not n.properties ? :{name}"
    if value is None:
        raise Invalid(f"el filtro de «{one.name}» necesita un valor")
    val = f"pv{i}"
    if one.op in ("eq", "ne"):
        if isinstance(value, bool):
            params[val] = "true" if value else "false"
        elif isinstance(value, int | float):
            params[val] = value
            same = (
                f"(jsonb_typeof(n.properties -> :{name}) = 'number' "
                f"and (n.properties ->> :{name})::numeric = :{val})"
            )
            return same if one.op == "eq" else f"not coalesce({same}, false)"
        else:
            params[val] = str(value)
        same = (
            f"(n.properties ->> :{name} = :{val} or (jsonb_typeof(n.properties -> :{name}) = "
            f"'array' and n.properties -> :{name} ? :{val}))"
        )
        return same if one.op == "eq" else f"not coalesce({same}, false)"
    operator = SQL_OPS[one.op]
    if isinstance(value, int | float) and not isinstance(value, bool):
        params[val] = value
        return (
            f"(jsonb_typeof(n.properties -> :{name}) = 'number' "
            f"and (n.properties ->> :{name})::numeric {operator} :{val})"
        )
    params[val] = str(value)
    return (
        f"(jsonb_typeof(n.properties -> :{name}) = 'string' "
        f"and n.properties ->> :{name} {operator} :{val})"
    )


async def search(
    connection: AsyncConnection,
    query: str | None = None,
    folder: str | None = None,
    tag: str | None = None,
    properties: list[PropertyFilter] | None = None,
    limit: int = 20,
    since: datetime | None = None,
    until: datetime | None = None,
    author: Author | None = None,
) -> list[Hit]:
    words = md.query_words(query or "")
    params: dict[str, Any] = {"limit": limit * 3 if words else limit}
    where = ["n.deleted_at is null"]
    changes = "null::int"
    if since is not None or until is not None:
        params["since"] = since or datetime(1970, 1, 1, tzinfo=MADRID)
        params["until"] = until or datetime.now(MADRID) + timedelta(minutes=1)
        where.append("n.updated_at >= :since and n.updated_at <= :until")
        changes = (
            "1 + (select count(*) from notebook.notebook_revision r where r.note_id = n.id "
            "and r.replaced_at >= :since and r.replaced_at <= :until)"
        )
    if author is not None:
        params["author"] = author
        where.append("n.updated_by = :author")
    if words:
        params["q"] = md.tsquery(query or "")
        where.append("n.search @@ to_tsquery('simple', :q)")
    if folder:
        params["folder"] = md.key(_folder(folder))
        where.append(
            "(n.folder_key = :folder or left(n.folder_key, length(:folder) + 1) = :folder || '/')"
        )
    if tag:
        params["tag"] = md.key(tag.lstrip("#")).strip("/")
        where.append(
            "exists (select 1 from notebook.notebook_tag t where t.note_id = n.id and "
            "(t.tag = :tag or left(t.tag, length(:tag) + 1) = :tag || '/'))"
        )
    for i, one in enumerate(properties or []):
        where.append(_property_sql(i, one, params))
    order = (
        "ts_rank(n.search, to_tsquery('simple', :q)) desc, n.updated_at desc"
        if words
        else "n.updated_at desc"
    )
    rows = (
        await connection.execute(
            text(
                "select n.id, n.folder, n.title, n.content, n.updated_at, n.updated_by, "
                f"n.updated_app, {changes} as changes, rec.app as source_app, "
                "rec.app_name as source_name, rec.href as source_href "
                "from notebook.notebook_note n left join lateral (select r.app, r.app_name, r.href "
                "  from notebook.notebook_record r where r.note_id = n.id and r.day is null "
                "  and not r.removed order by r.updated_at desc limit 1) rec on true "
                f"where {' and '.join(where)} "
                f"order by {order} limit :limit"
            ),
            params,
        )
    ).all()

    def in_title(row: Any) -> bool:
        folded = md.fold(row.title)
        return all(w in folded for w in words)

    ranked = sorted(rows, key=lambda r: not in_title(r)) if words else rows
    return [
        Hit(
            **_summary(r).model_dump(),
            snippet=md.snippet(r.content, query or ""),
            tags=md.tags(r.content),
            changes=r.changes if since is not None or until is not None else None,
            href=f"/notebook/nota/{r.id}",
            source=(
                Source(app=r.source_app, name=r.source_name, href=r.source_href)
                if r.source_app
                else None
            ),
        )
        for r in ranked[:limit]
    ]


class FolderOut(BaseModel):
    path: str
    name: str
    notes: int


class Listing(BaseModel):
    path: str
    folders: list[FolderOut]
    notes: list[NoteSummary]


async def list_folder(connection: AsyncConnection, path: str | None) -> Listing:
    clean = _folder(path)
    key = md.key(clean)
    if clean:
        exists = await connection.scalar(
            text("select 1 from notebook.notebook_folder where path_key = :key"), {"key": key}
        )
        if not exists:
            raise NotFound(f"la carpeta «{path}»")
        clean = await _folder_path(connection, clean)
    children = (
        await connection.execute(
            text(
                "select f.path, (select count(*) from notebook.notebook_note n "
                "  where n.deleted_at is null "
                "  and (n.folder_key = f.path_key "
                "       or left(n.folder_key, length(f.path_key) + 1) = f.path_key || '/')"
                ") as notes "
                "from notebook.notebook_folder f "
                "where (:key = '' and position('/' in f.path_key) = 0) or "
                "  (:key <> '' and left(f.path_key, length(:key) + 1) = :key || '/' "
                "   and position('/' in substr(f.path_key, length(:key) + 2)) = 0) "
                "order by lower(f.path)"
            ),
            {"key": key},
        )
    ).all()
    notes = (
        await connection.execute(
            text(
                "select id, folder, title, updated_at, updated_by from notebook.notebook_note "
                "where deleted_at is null and folder_key = :key order by lower(title)"
            ),
            {"key": key},
        )
    ).all()
    return Listing(
        path=clean,
        folders=[
            FolderOut(path=r.path, name=r.path.rsplit("/", 1)[-1], notes=r.notes) for r in children
        ],
        notes=[_summary(r) for r in notes],
    )


class Tree(BaseModel):
    folders: list[str]
    notes: list[NoteSummary]


async def tree(connection: AsyncConnection) -> Tree:
    folders = (
        await connection.execute(
            text("select path from notebook.notebook_folder order by lower(path)")
        )
    ).scalars()
    notes = (
        await connection.execute(
            text(
                "select id, folder, title, updated_at, updated_by from notebook.notebook_note "
                "where deleted_at is null order by lower(folder), lower(title)"
            )
        )
    ).all()
    return Tree(folders=list(folders), notes=[_summary(r) for r in notes])


class TagCount(BaseModel):
    tag: str
    notes: int


async def all_tags(connection: AsyncConnection) -> list[TagCount]:
    rows = (
        await connection.execute(
            text(
                "select t.tag, count(*) as notes from notebook.notebook_tag t "
                "join notebook.notebook_note n on n.id = t.note_id and n.deleted_at is null "
                "group by t.tag order by count(*) desc, t.tag"
            )
        )
    ).all()
    return [TagCount(tag=r.tag, notes=r.notes) for r in rows]


class Change(NoteSummary):
    changes: int


async def recent(
    connection: AsyncConnection,
    since: datetime,
    until: datetime | None = None,
    author: Author | None = None,
    limit: int = 50,
    apps: bool = True,
) -> list[Change]:
    rows = (
        await connection.execute(
            text(
                "select n.id, n.folder, n.title, n.updated_at, n.updated_by, n.updated_app, "
                "  1 + (select count(*) from notebook.notebook_revision r where r.note_id = n.id "
                "       and r.replaced_at >= :since and r.replaced_at <= :until) as changes "
                "from notebook.notebook_note n where n.deleted_at is null "
                "  and n.updated_at >= :since and n.updated_at <= :until "
                "  and (cast(:author as text) is null or n.updated_by = :author) "
                "  and (:apps or n.updated_app is null) "
                "order by n.updated_at desc limit :limit"
            ),
            {
                "since": since,
                "until": until or datetime.now(MADRID) + timedelta(minutes=1),
                "author": author,
                "limit": limit,
                "apps": apps,
            },
        )
    ).all()
    return [Change(**_summary(r).model_dump(), changes=r.changes) for r in rows]


class GraphNode(BaseModel):
    id: str
    title: str
    folder: str
    links: int
    depth: int | None = None


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[tuple[str, str]]


async def graph(connection: AsyncConnection, center: str | None = None, depth: int = 1) -> Graph:
    notes = (
        await connection.execute(
            text("select id, folder, title from notebook.notebook_note where deleted_at is null")
        )
    ).all()
    edges_rows = (
        await connection.execute(
            text(
                "select distinct l.note_id as source, "
                "  notebook.resolve(l.title_key, l.folder_key, s.folder_key) as target "
                "from notebook.notebook_link l "
                "join notebook.notebook_note s on s.id = l.note_id and s.deleted_at is null "
                "where l.kind = 'note' "
                "union "
                "select distinct l.note_id, r.note_id "
                "from notebook.notebook_link l "
                "join notebook.notebook_note s on s.id = l.note_id and s.deleted_at is null "
                "join notebook.notebook_record r on r.link_key = l.title_key and r.day is null "
                "  and not r.removed and r.note_id is not null "
                "join notebook.notebook_note t on t.id = r.note_id and t.deleted_at is null "
                "where l.kind = 'app'"
            )
        )
    ).all()
    edges = sorted(
        {
            (str(r.source), str(r.target))
            for r in edges_rows
            if r.target is not None and r.source != r.target
        }
    )
    degree: dict[str, int] = {}
    neighbours: dict[str, set[str]] = {}
    for a, b in edges:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
        neighbours.setdefault(a, set()).add(b)
        neighbours.setdefault(b, set()).add(a)
    by_id = {str(n.id): n for n in notes}
    distance: dict[str, int] | None = None
    if center is not None:
        start = (await find_row(connection, center)).id
        distance = {start: 0}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            if distance[current] >= depth:
                continue
            for other in sorted(neighbours.get(current, ())):
                if other not in distance:
                    distance[other] = distance[current] + 1
                    queue.append(other)
        by_id = {k: v for k, v in by_id.items() if k in distance}
        edges = [(a, b) for a, b in edges if a in by_id and b in by_id]
    return Graph(
        nodes=[
            GraphNode(
                id=k,
                title=v.title,
                folder=v.folder,
                links=degree.get(k, 0),
                depth=distance.get(k) if distance is not None else None,
            )
            for k, v in sorted(by_id.items(), key=lambda kv: (kv[1].folder, kv[1].title))
        ],
        edges=edges,
    )


class Settings(BaseModel):
    daily_folder: str
    review_property: str | None


async def settings(connection: AsyncConnection) -> Settings:
    found = (
        await connection.execute(
            text("select daily_folder, review_property from notebook.notebook_setting")
        )
    ).first()
    if found is None:
        return Settings(daily_folder="Diario", review_property=None)
    return Settings(daily_folder=found.daily_folder, review_property=found.review_property)


async def save_settings(connection: AsyncConnection, wanted: Settings) -> Settings:
    folder = _folder(wanted.daily_folder)
    if not folder:
        raise Invalid("el diario necesita una carpeta")
    review = (wanted.review_property or "").strip() or None
    await connection.execute(
        text(
            "insert into notebook.notebook_setting (daily_folder, review_property) "
            "values (:folder, :review) on conflict (user_id) do update "
            "set daily_folder = excluded.daily_folder, review_property = excluded.review_property"
        ),
        {"folder": folder, "review": review},
    )
    return await settings(connection)


class PropertyName(BaseModel):
    name: str
    notes: int
    dates: bool


async def property_names(connection: AsyncConnection) -> list[PropertyName]:
    rows = (
        await connection.execute(
            text(
                "select key as name, count(*) as notes, "
                "  bool_and(jsonb_typeof(value) = 'string' "
                "           and value #>> '{}' ~ '^\\d{4}-\\d{2}-\\d{2}') as dates "
                "from notebook.notebook_note, jsonb_each(properties) "
                "where deleted_at is null group by key order by count(*) desc, key"
            )
        )
    ).all()
    return [PropertyName(name=r.name, notes=r.notes, dates=bool(r.dates)) for r in rows]


class Due(NoteSummary):
    due: str


async def due_for_review(connection: AsyncConnection, limit: int = 50) -> list[Due] | None:
    chosen = (await settings(connection)).review_property
    if not chosen:
        return None
    rows = (
        await connection.execute(
            text(
                "select id, folder, title, updated_at, updated_by, properties ->> :name as due "
                "from notebook.notebook_note where deleted_at is null "
                "  and jsonb_typeof(properties -> :name) = 'string' "
                "  and left(properties ->> :name, 10) <= :today "
                "order by properties ->> :name, lower(title) limit :limit"
            ),
            {"name": chosen, "today": today().isoformat(), "limit": limit},
        )
    ).all()
    return [Due(**_summary(r).model_dump(), due=r.due[:10]) for r in rows]


async def daily_folder(connection: AsyncConnection) -> str:
    return (await settings(connection)).daily_folder


async def daily(
    connection: AsyncConnection, day: date | None, create_it: bool, author: Author
) -> Note | None:
    name = (day or today()).isoformat()
    folder = await daily_folder(connection)
    found = (
        await connection.execute(
            text(
                f"select {COLUMNS} from notebook.notebook_note where deleted_at is null "
                "and title_key = :title order by (folder_key = :folder) desc, length(folder_key) "
                "limit 1"
            ),
            {"title": name, "folder": md.key(folder)},
        )
    ).first()
    if found is not None:
        return _note(_row(found))
    if not create_it:
        return None
    return await create(connection, folder, name, "", author)
