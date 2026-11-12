from __future__ import annotations

import hmac
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.service import Service
from arga_tenancy import require_person
from notebook import export, files, mentions, notes, publisher, service, tools, widgets
from notebook import markdown as md
from notebook import panel as home_panel
from notebook.db import as_module
from notebook.notes import MADRID, ImportNote

MODULE_ID = "notebook"

app_service = Service(
    MODULE_ID,
    "Notebook",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    errors={notes.NotFound: 404, notes.Conflict: 409, notes.Invalid: 422},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = app_service.app
as_app = app_service.as_app


async def _run(action, *args):
    async with as_app() as connection:
        return await action(connection, *args)


def _id(value: UUID) -> str:
    return str(value)


class NoteOut(notes.Note):
    arga: notes.Owner | None = None


async def _note_out(action, *args) -> NoteOut:
    async def both(connection: AsyncConnection) -> NoteOut:
        found = await action(connection, *args)
        if isinstance(found, tuple):
            found = found[1]
        return NoteOut(**found.model_dump(), arga=await notes.owner(connection, found.id))

    return await _run(both)


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Notebook no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Notebook")
    served = service.SERVICES.get(capability)
    if served is None:
        raise HTTPException(status_code=404, detail=f"Notebook no sabe hacer '{capability}'")
    require_person()
    model, action = served
    try:
        asked = model.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return await _run(action, asked)


@app.get("/tree")
async def read_tree() -> notes.Tree:
    return await _run(notes.tree)


@app.get("/folders")
async def read_folder(path: str = "") -> notes.Listing:
    return await _run(notes.list_folder, path)


class FolderIn(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


@app.post("/folders", status_code=201)
async def create_folder(request: FolderIn) -> dict:
    return {"path": await _run(notes.create_folder, request.path)}


class FolderMove(BaseModel):
    source: str = Field(alias="from", min_length=1, max_length=1000)
    to: str = Field(min_length=1, max_length=1000)


@app.put("/folders")
async def move_folder(request: FolderMove) -> dict:
    moved = await _run(notes.move_folder, request.source, request.to, "app")
    return {"path": request.to, "notes": moved}


@app.delete("/folders")
async def delete_folder(path: str = Query(min_length=1)) -> dict:
    return {"trashed": await _run(notes.delete_folder, path)}


class NoteIn(BaseModel):
    folder: str = Field(default="", max_length=1000)
    title: str = Field(min_length=1, max_length=200)
    content: str = ""


@app.post("/notes", status_code=201)
async def create_note(request: NoteIn) -> NoteOut:
    return await _note_out(notes.create, request.folder, request.title, request.content, "app")


@app.get("/notes/resolve")
async def resolve_link(target: str = Query(min_length=1), source: UUID | None = None) -> dict:
    found = await _run(notes.link_target, target, str(source) if source else None)
    return {"note": found}


@app.get("/notes/{note_id}")
async def read_note(note_id: UUID) -> NoteOut:
    return await _note_out(notes.get, _id(note_id))


class LinksOut(BaseModel):
    links: list[notes.LinkOut]
    backlinks: list[notes.Backlink]


@app.get("/notes/{note_id}/links")
async def read_links(note_id: UUID) -> LinksOut:
    async def both(connection: AsyncConnection) -> LinksOut:
        return LinksOut(
            links=await notes.links_of(connection, _id(note_id)),
            backlinks=await notes.backlinks(connection, _id(note_id)),
        )

    return await _run(both)


class WriteIn(BaseModel):
    content: str
    version: int | None = None


@app.put("/notes/{note_id}")
async def write_note(note_id: UUID, request: WriteIn) -> NoteOut:
    return await _note_out(notes.write, _id(note_id), request.content, request.version, "app")


class PropertiesIn(BaseModel):
    set: dict[str, Any] = Field(default_factory=dict)
    remove: list[str] = Field(default_factory=list)


@app.put("/notes/{note_id}/properties")
async def write_properties(note_id: UUID, request: PropertiesIn) -> NoteOut:
    return await _note_out(
        notes.edit,
        _id(note_id),
        lambda content: md.set_properties(content, request.set, request.remove),
        "app",
    )


class MoveIn(BaseModel):
    folder: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=200)


@app.post("/notes/{note_id}/move")
async def move_note(note_id: UUID, request: MoveIn) -> dict:
    async def both(connection: AsyncConnection) -> dict:
        moved, relinked = await notes.move(
            connection, _id(note_id), request.folder, request.title, "app"
        )
        owner = await notes.owner(connection, moved.id)
        return {"note": NoteOut(**moved.model_dump(), arga=owner), "relinked": relinked}

    return await _run(both)


@app.delete("/notes/{note_id}", status_code=204)
async def trash_note(note_id: UUID) -> Response:
    await _run(notes.trash, _id(note_id))
    return Response(status_code=204)


@app.get("/notes/{note_id}/revisions")
async def list_revisions(note_id: UUID) -> list[notes.Revision]:
    return await _run(notes.revisions, _id(note_id))


@app.get("/notes/{note_id}/revisions/{revision_id}")
async def read_revision(note_id: UUID, revision_id: UUID) -> notes.RevisionFull:
    return await _run(notes.revision, _id(note_id), _id(revision_id))


@app.post("/notes/{note_id}/revisions/{revision_id}/restore")
async def restore_revision(note_id: UUID, revision_id: UUID) -> NoteOut:
    return await _note_out(notes.restore_revision, _id(note_id), _id(revision_id), "app")


@app.get("/trash")
async def read_trash() -> list[notes.Trashed]:
    return await _run(notes.trashed)


@app.post("/trash/{note_id}/restore")
async def restore_note(note_id: UUID) -> NoteOut:
    return await _note_out(notes.restore, _id(note_id))


@app.delete("/trash/{note_id}")
async def delete_note(note_id: UUID) -> dict:
    return {"deleted": await _run(notes.empty_trash, _id(note_id))}


@app.delete("/trash")
async def empty_trash() -> dict:
    return {"deleted": await _run(notes.empty_trash, None)}


class ImportIn(BaseModel):
    notes: list[ImportNote] = Field(max_length=500)


@app.post("/import")
async def import_notes(request: ImportIn) -> notes.Imported:
    return await _run(notes.import_notes, request.notes)


@app.post("/files", status_code=201)
async def upload_file(request: Request, name: str = Query(min_length=1, max_length=200)) -> dict:
    data = await request.body()
    saved = await _run(files.save, name, data)
    return saved.model_dump()


@app.get("/files/{name}")
async def read_file(name: str) -> Response:
    data, kind, digest = await _run(files.read, name)
    return Response(
        content=data,
        media_type=kind,
        headers={
            "cache-control": "private, max-age=86400",
            "etag": f'"{digest[:32]}"',
            "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "x-content-type-options": "nosniff",
        },
    )


@app.get("/search")
async def search(
    q: str | None = Query(default=None, max_length=300),
    folder: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[notes.Hit]:
    return await _run(notes.search, q, folder, tag, [], limit)


class Found(BaseModel):
    title: str
    detail: str | None = None
    href: str


class Results(BaseModel):
    results: list[Found]


@app.get("/search/arga")
async def search_arga(
    q: str = Query(default="", max_length=300), limit: int = Query(default=8, ge=1, le=50)
) -> Results:
    words = q.strip()[:200]
    if not md.query_words(words):
        return Results(results=[])
    hits = await _run(notes.search, words, None, None, [], limit)
    found = []
    for hit in hits:
        if hit.source is not None:
            where = hit.folder.split("/", 1)[1] if "/" in hit.folder else ""
            detail = " · ".join(part for part in (hit.source.name, where) if part)
            found.append(Found(title=hit.title[:160], detail=detail[:200], href=hit.source.href))
        else:
            detail = f"Nota · {hit.folder}" if hit.folder else "Nota"
            found.append(Found(title=hit.title[:160], detail=detail[:200], href=hit.href))
    return Results(results=found)


@app.get("/tags")
async def read_tags() -> list[notes.TagCount]:
    return await _run(notes.all_tags)


@app.get("/recent")
async def read_recent(days: int = Query(default=7, ge=1, le=365)) -> list[notes.Change]:
    since = datetime.combine(notes.today() - timedelta(days=days), time(), MADRID)
    return await _run(notes.recent, since, None, None, 50)


@app.get("/graph")
async def read_graph(
    center: UUID | None = None, depth: int = Query(default=1, ge=1, le=3)
) -> notes.Graph:
    return await _run(notes.graph, _id(center) if center else None, depth)


@app.post("/daily")
async def open_daily(day: date | None = None) -> NoteOut:
    return await _note_out(notes.daily, day, True, "app")


@app.get("/export")
async def read_export() -> export.State:
    return await _run(export.state)


@app.post("/export")
async def push_export() -> export.State:
    await export.push(as_module, hub_client())
    return await _run(export.state)


def hub_client() -> httpx.AsyncClient:
    return app_service.client()


@app.get("/linkables")
async def read_linkables() -> list[dict]:
    return await _run(mentions.linkables)


@app.get("/settings")
async def read_settings() -> notes.Settings:
    return await _run(notes.settings)


@app.put("/settings")
async def write_settings(request: notes.Settings) -> notes.Settings:
    return await _run(notes.save_settings, request)


@app.get("/properties")
async def read_property_names() -> list[notes.PropertyName]:
    return await _run(notes.property_names)


@app.get("/review")
async def read_review() -> dict:
    due = await _run(notes.due_for_review)
    return {"chosen": due is not None, "notes": due or []}


app_service.serve_ui()
