from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import kernel_url, user_headers
from notebook import markdown as md

MODULE = "notebook"
CAPABILITY = "notes.push"
FILES = "Adjuntos"


class State(BaseModel):
    pushed_at: datetime | None
    tried_at: datetime | None
    outcome: str | None
    detail: str | None
    commit_url: str | None
    pending: int


class Change(BaseModel):
    texts: dict[str, str]
    binaries: dict[str, str]
    deletes: list[str]
    hashes: dict[str, str]
    by_claude: int

    @property
    def empty(self) -> bool:
        return not (self.texts or self.binaries or self.deletes)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


CARDS = text("""
    select r.link_key, r.title, n.folder, n.title as note_title
    from notebook.notebook_record r
    join notebook.notebook_note n on n.id = r.note_id and n.deleted_at is null
    where r.day is null and not r.removed
""")


def obsidian(content: str, cards: dict[str, tuple[str, str]]) -> str:
    out = content
    for link in reversed(md.links(content)):
        found = cards.get(link.title_key) if link.kind == "app" else None
        if found is None:
            continue
        path, title = found
        pipe = "\\|" if link.escaped_pipe else "|"
        shown = (link.alias or md.safe_title(title)).replace("]", ")")
        rebuilt = ("!" if link.embed else "") + "[[" + path
        if link.heading:
            rebuilt += "#" + link.heading
        rebuilt += pipe + shown + "]]"
        out = out[: link.start] + rebuilt + out[link.end :]
    return out


async def change(connection: AsyncConnection) -> Change:
    exported = {
        row.path: row.sha256
        for row in (
            await connection.execute(text("select path, sha256 from notebook.notebook_exported"))
        ).all()
    }
    texts: dict[str, str] = {}
    binaries: dict[str, str] = {}
    hashes: dict[str, str] = {}
    by_claude = 0
    notes = (
        await connection.execute(
            text(
                "select folder, title, content, updated_by from notebook.notebook_note "
                "where deleted_at is null"
            )
        )
    ).all()
    cards = {
        row.link_key: (md.path_of(row.folder, row.note_title), row.title)
        for row in (await connection.execute(CARDS)).all()
    }
    wanted: set[str] = set()
    for note in notes:
        path = md.path_of(note.folder, note.title) + ".md"
        wanted.add(path)
        written = obsidian(note.content, cards)
        digest = _sha(written.encode())
        if exported.get(path) != digest:
            texts[path] = written
            hashes[path] = digest
            by_claude += note.updated_by == "tool"
    files = (
        await connection.execute(text("select name, sha256 from notebook.notebook_file"))
    ).all()
    for one in files:
        path = f"{FILES}/{one.name}"
        wanted.add(path)
        if exported.get(path) != one.sha256:
            content = await connection.scalar(
                text("select content from notebook.notebook_file where name = :name"),
                {"name": one.name},
            )
            binaries[path] = base64.b64encode(bytes(content)).decode()
            hashes[path] = one.sha256
    deletes = sorted(path for path in exported if path not in wanted)
    return Change(
        texts=texts, binaries=binaries, deletes=deletes, hashes=hashes, by_claude=by_claude
    )


PER_PUSH = 400


def batch(found: Change, limit: int = PER_PUSH) -> Change:
    paths = sorted([*found.texts, *found.binaries, *found.deletes])[:limit]
    if len(paths) == len(found.texts) + len(found.binaries) + len(found.deletes):
        return found
    keep = set(paths)
    texts = {path: value for path, value in found.texts.items() if path in keep}
    return Change(
        texts=texts,
        binaries={path: value for path, value in found.binaries.items() if path in keep},
        deletes=[path for path in found.deletes if path in keep],
        hashes={path: value for path, value in found.hashes.items() if path in keep},
        by_claude=found.by_claude if len(texts) == len(found.texts) else 0,
    )


def message(found: Change) -> str:
    changed = len(found.texts) + len(found.binaries)
    parts = []
    if changed:
        parts.append(f"{changed} {'change' if changed == 1 else 'changes'}")
    if found.deletes:
        parts.append(
            f"{len(found.deletes)} {'deletion' if len(found.deletes) == 1 else 'deletions'}"
        )
    line = "Notebook: " + (", ".join(parts) or "nothing")
    if found.by_claude:
        line += f" (Claude in {found.by_claude})"
    names = sorted([*found.texts, *found.binaries, *found.deletes])[:20]
    return line + "\n\n" + "\n".join(f"- {name}" for name in names)


def key(found: Change) -> str:
    summary = json.dumps(
        {"write": found.hashes, "delete": found.deletes}, sort_keys=True, ensure_ascii=False
    )
    return "notebook:" + _sha(summary.encode())


async def state(connection: AsyncConnection) -> State:
    found = (
        await connection.execute(
            text(
                "select pushed_at, tried_at, outcome, detail, commit_url from notebook.notebook_export"
            )
        )
    ).first()
    pending = await change(connection)
    count = len(pending.texts) + len(pending.binaries) + len(pending.deletes)
    if found is None:
        return State(
            pushed_at=None, tried_at=None, outcome=None, detail=None, commit_url=None, pending=count
        )
    return State(**found._asdict(), pending=count)


async def _record(
    connection: AsyncConnection, outcome: str, detail: str | None, url: str | None, ok: bool
) -> None:
    await connection.execute(
        text(
            "insert into notebook.notebook_export (tried_at, pushed_at, outcome, detail, commit_url) "
            "values (now(), case when :ok then now() end, :outcome, :detail, :url) "
            "on conflict (user_id) do update set tried_at = now(), "
            "pushed_at = case when :ok then now() else notebook.notebook_export.pushed_at end, "
            "outcome = :outcome, detail = :detail, "
            "commit_url = coalesce(:url, notebook.notebook_export.commit_url)"
        ),
        {"ok": ok, "outcome": outcome, "detail": (detail or "")[:500] or None, "url": url},
    )


async def _accept(connection: AsyncConnection, found: Change) -> None:
    for path, digest in found.hashes.items():
        await connection.execute(
            text(
                "insert into notebook.notebook_exported (path, sha256) values (:path, :sha) "
                "on conflict (user_id, path) do update set sha256 = excluded.sha256"
            ),
            {"path": path, "sha": digest},
        )
    if found.deletes:
        await connection.execute(
            text("delete from notebook.notebook_exported where path = any(:paths)"),
            {"paths": found.deletes},
        )


async def ask(client: httpx.AsyncClient, body: dict[str, Any]) -> httpx.Response:
    return await client.post(
        f"{kernel_url()}/internal/capabilities/{CAPABILITY}",
        json=body,
        headers={**user_headers(), "x-arga-module": MODULE},
        timeout=120.0,
    )


async def push(begin, client: httpx.AsyncClient) -> dict[str, Any]:
    async with begin() as connection:
        found = batch(await change(connection))
    if found.empty:
        return {"outcome": "nothing"}
    body = {
        "key": key(found),
        "message": message(found),
        "files": [{"path": p, "text": t} for p, t in found.texts.items()]
        + [{"path": p, "base64": b} for p, b in found.binaries.items()],
        "deletes": found.deletes,
    }
    try:
        response = await ask(client, body)
    except httpx.HTTPError as error:
        async with begin() as connection:
            await _record(
                connection, "error", f"Hub does not answer ({type(error).__name__})", None, False
            )
        return {"outcome": "error"}
    if response.status_code == 404:
        detail = response.json().get("detail") if response.content else None
        async with begin() as connection:
            await _record(
                connection, "unconnected", detail or "no GitHub repository connected", None, False
            )
        return {"outcome": "unconnected"}
    if response.status_code != 200:
        async with begin() as connection:
            await _record(connection, "error", f"Hub contesta {response.status_code}", None, False)
        return {"outcome": "error"}
    answer = response.json()
    outcome = answer.get("outcome")
    async with begin() as connection:
        if outcome == "ok":
            await _accept(connection, found)
            await _record(connection, "ok", None, answer.get("url"), True)
        else:
            await _record(
                connection,
                outcome if outcome == "skipped" else "error",
                answer.get("detail"),
                None,
                False,
            )
    return {"outcome": outcome, "url": answer.get("url")}
