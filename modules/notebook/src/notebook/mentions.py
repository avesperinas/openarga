from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from notebook import markdown as md

TYPE = "notebook.mention"

LINKABLES = text(f"""
    select distinct on (module, payload->'{contracts.LINKABLE}'->>'id')
        module, payload->'{contracts.LINKABLE}' as item
    from notebook.events
    where payload ? '{contracts.LINKABLE}' and module <> 'notebook'
    order by module, payload->'{contracts.LINKABLE}'->>'id', ts desc, ingested_at desc
""")


CARDS = text("""
    select app, record_id, title, kind, href, note_id
    from notebook.notebook_record
    where day is null and not removed and note_id is not null
""")


async def linkables(connection: AsyncConnection) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in (await connection.execute(LINKABLES)).all():
        if row.item.get("removed"):
            continue
        target = f"{row.module}:{row.item['id']}"
        found[target] = {
            "app": row.module,
            "id": row.item["id"],
            "target": target,
            "title": row.item["title"],
            "kind": row.item["kind"],
            "href": row.item["href"],
            "note_id": None,
        }
    for row in (await connection.execute(CARDS)).all():
        target = f"{row.app}:{row.record_id}"
        found[target] = {
            "app": row.app,
            "id": row.record_id,
            "target": target,
            "title": row.title,
            "kind": row.kind,
            "href": row.href,
            "note_id": str(row.note_id),
        }
    return sorted(found.values(), key=lambda one: (one["kind"], one["title"].casefold()))


def _split(target: str) -> tuple[str, str] | None:
    app, _, ref = target.partition(":")
    if not app or not ref or not md.APP_LINK.match(target):
        return None
    return app, ref


async def _announce(
    connection: AsyncConnection, note_id: str, target: str, title: str, line: str, removed: bool
) -> None:
    parts = _split(target)
    if parts is None:
        return
    app, ref = parts
    try:
        body = contracts.mention(
            app=app,
            id=ref[:100],
            note_id=note_id,
            note_title=title[:200],
            note_href=f"/notebook/note/{note_id}",
            line=line[:500],
            removed=removed,
        )
    except contracts.BadContract:
        return
    await connection.execute(
        text(
            "insert into notebook.notebook_outbox (type, payload, dedup_hash) "
            "values (:type, cast(:payload as jsonb), :dedup) "
            "on conflict (user_id, dedup_hash) do nothing"
        ),
        {
            "type": TYPE,
            "payload": json.dumps({contracts.MENTION: body}),
            "dedup": f"mention:{note_id}:{target}:{datetime.now(UTC).isoformat()}:{removed}",
        },
    )


async def sync(connection: AsyncConnection, note_id: str, *, gone: bool = False) -> None:
    note = (
        await connection.execute(
            text("select title, content from notebook.notebook_note where id = :id"),
            {"id": note_id},
        )
    ).one_or_none()
    now: dict[str, str] = {}
    if note is not None and not gone:
        theirs = md.block(note.content)
        for link in md.links(note.content):
            if theirs is not None and theirs.start <= link.start < theirs.end:
                continue
            if link.kind == "app" and link.target not in now:
                now[link.target] = md.line(note.content, link.line)
    before = {
        row.target: row
        for row in (
            await connection.execute(
                text(
                    "select target, title, line from notebook.notebook_mention where note_id = :id"
                ),
                {"id": note_id},
            )
        ).all()
    }
    title = note.title if note is not None else ""
    for target, line in now.items():
        old = before.get(target)
        if old is not None and old.title == title and old.line == line:
            continue
        await _announce(connection, note_id, target, title, line, False)
        await connection.execute(
            text(
                "insert into notebook.notebook_mention (note_id, target, title, line) "
                "values (:note, :target, :title, :line) on conflict (note_id, target) "
                "do update set title = excluded.title, line = excluded.line"
            ),
            {"note": note_id, "target": target, "title": title, "line": line},
        )
    for target, old in before.items():
        if target in now:
            continue
        await _announce(connection, note_id, target, old.title, old.line, True)
        await connection.execute(
            text(
                "delete from notebook.notebook_mention where note_id = :note and target = :target"
            ),
            {"note": note_id, "target": target},
        )
