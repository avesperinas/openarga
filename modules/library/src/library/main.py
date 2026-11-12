from __future__ import annotations

import hmac
import os
import unicodedata
from pathlib import Path
from uuid import UUID

from fastapi import Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_module.service import Service
from arga_tenancy import require_person
from library import isbn, library, publisher, stats, tools, widgets
from library import panel as home_panel

MODULE_ID = "library"

service = Service(
    MODULE_ID,
    "Library",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    errors={library.NotFound: 404, library.Conflict: 409},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
_edit = service.edit
hub_client = service.client


def _plain(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join("".join(c if c.isalnum() else " " for c in folded.lower()).split())


async def want(connection: AsyncConnection, asked: contracts.BooksWant, client_of) -> dict:
    title = _plain(asked.title)
    for one in await library.books(connection):
        if (asked.isbn13 and one.isbn13 == asked.isbn13) or _plain(one.title) == title:
            return contracts.books_wanted(
                book_id=one.id, already=True, resolved=one.edition == "catalog"
            )
    reading = library.ReadingIn(status="want", note=asked.note)
    fallback = library.EditionIn(title=asked.title, authors=list(asked.authors))
    wanted = isbn.to_isbn13(asked.isbn13) if asked.isbn13 else None
    if wanted:
        added = await library.add_by_isbn(connection, client_of(), wanted, fallback, reading, "app")
    else:
        added = await library.add_manual(
            connection, library.ManualBookIn(edition=fallback, reading=reading), source="app"
        )
    return contracts.books_wanted(
        book_id=added.id, already=False, resolved=added.edition == "catalog"
    )


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Library no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Library")
    if capability != contracts.BOOKS_WANT:
        raise HTTPException(status_code=404, detail=f"Library no sabe hacer '{capability}'")
    require_person()
    try:
        asked = contracts.BooksWant.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    answer = await _edit(want, asked, hub_client)
    print(f"quiero leerlo · pedido por {x_arga_module}", flush=True)
    return answer


@app.get("/genres")
async def read_genres() -> list[library.GenreOut]:
    return library.genres()


@app.get("/books")
async def list_books(
    status: library.Status | None = None,
    year: int | None = Query(default=None, ge=1900, le=2200),
) -> list[library.Book]:
    return await _edit(library.books, status, year)


@app.post("/books", status_code=201)
async def add_book(request: library.ManualBookIn) -> library.Book:
    return await _edit(library.add_manual, request)


@app.get("/catalog/search")
async def search_catalog(q: str = Query(min_length=2, max_length=120)) -> library.SearchOut:
    return await _edit(library.search, q, hub_client())


@app.post("/books/catalog", status_code=201)
async def add_from_catalog(request: library.CatalogBookIn) -> library.Book:
    return await _edit(library.add_from_catalog, request, hub_client())


@app.put("/books/{reading_id}/resolve")
async def resolve_book(reading_id: UUID, request: library.ResolveIn) -> library.Book:
    return await _edit(library.resolve, str(reading_id), request, hub_client())


@app.get("/stats")
async def read_stats(year: int | None = Query(default=None, ge=1900, le=2200)) -> stats.YearStats:
    return await _edit(stats.year_stats, year)


@app.put("/goals/{year}")
async def set_goal(year: int, request: stats.GoalIn) -> stats.YearStats:
    if not 2000 <= year <= 2200:
        raise HTTPException(status_code=422, detail="ese año no vale")
    return await _edit(stats.set_goal, year, request)


@app.get("/books/{reading_id}/cover")
async def read_cover(reading_id: UUID) -> Response:
    image, kind, edition_id = await _edit(library.cover, str(reading_id))
    return Response(
        content=image,
        media_type=kind,
        headers={"cache-control": "private, max-age=86400", "etag": f'"{edition_id}"'},
    )


@app.get("/books/{reading_id}")
async def read_book(reading_id: UUID) -> library.Book:
    return await _edit(library.book, str(reading_id))


@app.put("/books/{reading_id}")
async def update_reading(reading_id: UUID, request: library.ReadingIn) -> library.Book:
    return await _edit(library.update_reading, str(reading_id), request)


@app.put("/books/{reading_id}/edition")
async def update_edition(reading_id: UUID, request: library.EditionIn) -> library.Book:
    return await _edit(library.update_edition, str(reading_id), request)


@app.post("/books/{reading_id}/start")
async def start_reading(reading_id: UUID, request: library.StartIn) -> library.Book:
    return await _edit(library.start, str(reading_id), request)


@app.post("/books/{reading_id}/finish")
async def finish_reading(reading_id: UUID, request: library.FinishIn) -> library.Book:
    return await _edit(library.finish, str(reading_id), request)


service.serve_ui()
