from __future__ import annotations

import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_tenancy import kernel_url, user_headers
from notebook import cards, notes
from notebook import markdown as md

MODULE = "notebook"
KEY = contracts.RECORD
AUTHOR = "import"
WINDOW = timedelta(days=2)
BEGINNING = datetime(1970, 1, 1, tzinfo=UTC)

LATEST = text(f"""
    select distinct on (module, payload->'{KEY}'->>'id')
        module, ingested_at, payload->'{KEY}' as item
    from notebook.events
    where module <> '{MODULE}' and payload ? '{KEY}' and ts >= :since
    order by module, payload->'{KEY}'->>'id', ingested_at desc, ts desc
""")

KNOWN = text("""
    select app, record_id, app_name, kind, day, properties, removed, note_id, seen_at
    from notebook.notebook_record
""")

UPSERT = text("""
    insert into notebook.notebook_record (app, record_id, link_key, app_name, title, kind, href, folder,
                                    day, properties, body, removed, seen_at)
    values (:app, :record_id, :link_key, :app_name, :title, :kind, :href, :folder, :day,
            cast(:properties as jsonb), :body, :removed, :seen)
    on conflict (user_id, app, record_id) do update
    set title = excluded.title, kind = excluded.kind, href = excluded.href,
        folder = excluded.folder, day = excluded.day, properties = excluded.properties,
        body = excluded.body, removed = excluded.removed, seen_at = excluded.seen_at,
        updated_at = now()
    returning note_id, placed_folder, placed_title
""")

PLACED = text("""
    update notebook.notebook_record
    set note_id = :note, placed_folder = :folder, placed_title = :title
    where app = :app and record_id = :record_id
""")

OF_DAY = text("""
    select app, app_name, record_id, title, kind, href, day, properties, body, removed, note_id
    from notebook.notebook_record
    where day = :day
""")


def kernel_transport() -> httpx.AsyncBaseTransport | None:
    return None


async def app_names() -> dict[str, str]:
    try:
        async with httpx.AsyncClient(transport=kernel_transport(), timeout=5.0) as client:
            response = await client.get(f"{kernel_url()}/modules", headers=user_headers())
        if response.status_code == 200:
            return {one["id"]: one["name"] for one in response.json()}
    except httpx.HTTPError:
        pass
    return {}


_TOLD: set[tuple[str, str, datetime]] = set()


def _ref(item: Any) -> str:
    return str(item.get("id")) if isinstance(item, dict) else ""


def _valid(module: str, item: Any, at: datetime) -> dict[str, Any] | None:
    try:
        if not isinstance(item, dict):
            raise contracts.BadContract("record does not match: it is not an object")
        return contracts.record(**item)
    except (contracts.BadContract, TypeError) as error:
        if (module, _ref(item), at) not in _TOLD:
            _TOLD.add((module, _ref(item), at))
            print(f"records · dropped {module}:{_ref(item)}: {error}", file=sys.stderr, flush=True)
        return None


@dataclass
class Result:
    notes: int = 0
    days: int = 0
    removed: int = 0
    skipped: int = 0

    def asdict(self) -> dict[str, int]:
        return {
            "notes": self.notes,
            "days": self.days,
            "removed": self.removed,
            "skipped": self.skipped,
        }


async def derive(
    connection: AsyncConnection,
    full: bool = True,
    names: Callable[[], Awaitable[dict[str, str]]] = app_names,
) -> dict[str, int]:
    since = BEGINNING if full else datetime.now(UTC) - WINDOW
    known = {(row.app, row.record_id): row for row in await connection.execute(KNOWN)}
    fresh = [
        row
        for row in (await connection.execute(LATEST, {"since": since})).all()
        if (row.module, _ref(row.item)) not in known
        or known[(row.module, _ref(row.item))].seen_at < row.ingested_at
    ]
    result = Result()
    if not fresh:
        return result.asdict()
    named = {row.app: row.app_name for row in known.values()}
    if any(row.module not in named for row in fresh):
        found = await names()
        for app in {row.module for row in fresh} - set(named):
            named[app] = (found.get(app) or app.capitalize())[:80]

    days: dict[date, _Day] = {}
    for row in fresh:
        item = _valid(row.module, row.item, row.ingested_at)
        if item is None:
            result.skipped += 1
            continue
        try:
            async with connection.begin_nested():
                await _apply(connection, row, item, known, named, days, result)
        except Exception as error:  # noqa: BLE001
            _say_once(row.module, item["id"], row.ingested_at, error)
            result.skipped += 1

    for when, touched in sorted(days.items()):
        try:
            async with connection.begin_nested():
                if await _day(connection, when, touched):
                    result.days += 1
        except Exception as error:  # noqa: BLE001
            _say_once("day", when.isoformat(), BEGINNING, error)
    return result.asdict()


def _say_once(where: str, ref: str, at: datetime, error: Exception) -> None:
    if (where, ref, at) in _TOLD:
        return
    _TOLD.add((where, ref, at))
    print(f"records · {where}:{ref}: {type(error).__name__}: {error}", file=sys.stderr, flush=True)


async def _apply(
    connection: AsyncConnection,
    row: Any,
    item: dict[str, Any],
    known: dict[tuple[str, str], Any],
    named: dict[str, str],
    days: dict[date, _Day],
    result: Result,
) -> None:
    before = known.get((row.module, item["id"]))
    day = date.fromisoformat(item["day"]) if item["day"] else None
    found = (
        await connection.execute(
            UPSERT,
            {
                "app": row.module,
                "record_id": item["id"],
                "link_key": cards.link_key(row.module, item["id"]),
                "app_name": named[row.module],
                "title": item["title"],
                "kind": item["kind"],
                "href": item["href"],
                "folder": item["folder"],
                "day": day,
                "properties": json.dumps(item["properties"], ensure_ascii=False),
                "body": item["body"],
                "removed": item["removed"],
                "seen": row.ingested_at,
            },
        )
    ).one()
    placed = Placed(found.note_id, found.placed_folder, found.placed_title)
    for when, was in ((before.day if before else None, before), (day, None)):
        if when is not None:
            touched = days.setdefault(when, _Day())
            touched.apps.add(named[row.module])
            if was is not None:
                touched.before.update(was.properties)
    old = _owned_before(before)
    if day is not None:
        if before is not None and before.day is None and before.note_id is not None:
            exists, trashed = await _alive(connection, before.note_id)
            if exists and not trashed:
                await _remove(connection, str(before.note_id), old, named[row.module])
        return
    if before is not None and before.day is not None:
        placed = Placed(None, None, None)
    outcome = await _note(connection, row.module, named[row.module], item, placed, old)
    if outcome == "removed":
        result.removed += 1
    elif outcome == "written":
        result.notes += 1


@dataclass(frozen=True)
class Placed:
    note_id: Any
    placed_folder: str | None
    placed_title: str | None


def _owned_before(before: Any) -> dict[str, Any]:
    if before is None or before.day is not None:
        return {}
    return {"arga": f"{before.app}:{before.record_id}", "type": before.kind, **before.properties}


@dataclass
class _Day:
    apps: set[str]
    before: dict[str, Any]

    def __init__(self) -> None:
        self.apps = set()
        self.before = {}


def _place(app_name: str, folder: str) -> str:
    try:
        return md.folder(f"{md.safe_title(app_name)}/{folder}")
    except md.InvalidName:
        return md.folder(md.safe_title(app_name))


async def _create(
    connection: AsyncConnection, folder: str, title: str, content: str, app_name: str
) -> notes.Note:
    for attempt in range(1, 100):
        wanted = title if attempt == 1 else md.safe_title(f"{title} ({attempt})")
        try:
            return await notes.create(connection, folder, wanted, content, AUTHOR, app_name)
        except notes.Conflict:
            continue
    raise notes.Conflict(f"there is no free title for '{title}' in '{folder}'")


async def _move(
    connection: AsyncConnection, note_id: str, folder: str, title: str, app_name: str
) -> notes.Note:
    for attempt in range(1, 100):
        wanted = title if attempt == 1 else md.safe_title(f"{title} ({attempt})")
        try:
            moved, _ = await notes.move(connection, note_id, folder, wanted, AUTHOR, app_name)
            return moved
        except notes.Conflict:
            continue
    raise notes.Conflict(f"there is no free title for '{title}' in '{folder}'")


async def _alive(connection: AsyncConnection, note_id: Any) -> tuple[bool, bool]:
    if note_id is None:
        return False, False
    found = (
        await connection.execute(
            text("select deleted_at from notebook.notebook_note where id = :id"), {"id": note_id}
        )
    ).first()
    if found is None:
        return False, False
    return True, found.deleted_at is not None


async def _note(
    connection: AsyncConnection,
    app: str,
    app_name: str,
    item: dict[str, Any],
    placed: Placed,
    before: dict[str, Any],
) -> str:
    exists, trashed = await _alive(connection, placed.note_id)
    if trashed:
        return "kept"
    params = {"app": app, "record_id": item["id"]}
    if item["removed"]:
        if exists:
            await _remove(connection, str(placed.note_id), before, app_name)
        await connection.execute(PLACED, {**params, "note": None, "folder": None, "title": None})
        return "removed"
    one = cards.Card(
        app=app,
        app_name=app_name,
        record_id=item["id"],
        title=item["title"],
        kind=item["kind"],
        href=item["href"],
        properties=item["properties"],
        body=item["body"],
    )
    wanted = cards.owned([one])
    folder = _place(app_name, item["folder"])
    title = md.safe_title(item["title"])
    if not exists:
        created = await _create(connection, folder, title, cards.compose("", wanted), app_name)
        await connection.execute(
            PLACED, {**params, "note": created.id, "folder": folder, "title": title}
        )
        return "written"
    note_id = str(placed.note_id)
    current = await notes._by_id(connection, note_id)
    if (folder, title) != (placed.placed_folder, placed.placed_title):
        where = folder if current.folder == placed.placed_folder else current.folder
        await _move(connection, note_id, where, title, app_name)
        await connection.execute(
            PLACED, {**params, "note": note_id, "folder": folder, "title": title}
        )
        current = await notes._by_id(connection, note_id)
    content = cards.compose(current.content, wanted, before)
    await notes._save(connection, current, content, AUTHOR, app=app_name)
    return "written"


async def _remove(
    connection: AsyncConnection, note_id: str, before: dict[str, Any], app_name: str
) -> None:
    current = await notes._by_id(connection, note_id)
    left = cards.compose(current.content, None, before)
    if not md.outside_block(left).strip() and not md.properties(left):
        await notes.trash(connection, note_id)
        return
    await notes._save(connection, current, left, AUTHOR, app=app_name)


async def _day(connection: AsyncConnection, day: date, touched: _Day) -> bool:
    rows = (await connection.execute(OF_DAY, {"day": day})).all()
    active = [notes.card(row) for row in rows if not row.removed]
    note_id = next((row.note_id for row in rows if row.note_id is not None), None)
    exists, trashed = await _alive(connection, note_id)
    if trashed:
        return False
    if not exists:
        if not active:
            return False
        daily = await notes.daily(connection, day, True, AUTHOR)
        assert daily is not None
        note_id = daily.id
    current = await notes._by_id(connection, str(note_id))
    wanted = cards.owned(active)
    content = cards.compose(current.content, wanted, touched.before)
    await notes._save(connection, current, content, AUTHOR, app=", ".join(sorted(touched.apps)))
    await connection.execute(
        text("update notebook.notebook_record set note_id = :note where day = :day"),
        {"note": str(note_id), "day": day},
    )
    return True
