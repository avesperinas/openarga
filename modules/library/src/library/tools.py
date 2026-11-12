from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from library import isbn, library, stats
from library.library import Format, Genre, Status

MODULE = "library"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _book(one: library.Book) -> dict[str, Any]:
    return {
        "book_id": one.id,
        "title": one.title,
        "authors": one.authors,
        "pages": one.pages,
        "language": one.language,
        "isbn13": one.isbn13,
        "status": one.status,
        "started_on": one.started_on.isoformat() if one.started_on else None,
        "finished_on": one.finished_on.isoformat() if one.finished_on else None,
        "days": one.days,
        "rating": one.rating,
        "format": one.format,
        "genre": one.genre,
        "note": one.note,
        "edition": one.edition,
    }


class FindBooks(BaseModel):
    query: str | None = Field(
        default=None, max_length=100, description="Parte del título o del nombre de un autor."
    )
    genre: Genre | None = None
    status: Status | None = None
    year: int | None = Field(
        default=None, ge=1900, le=2200, description="Año de lectura: el de fin, o el de inicio."
    )
    limit: int = Field(default=50, ge=1, le=500)


async def find_books(connection: AsyncConnection, arguments: FindBooks) -> dict[str, Any]:
    found = await library.find(
        connection,
        arguments.query,
        arguments.genre,
        arguments.status,
        arguments.year,
        arguments.limit,
    )
    today = library.today()
    books = []
    for one in found:
        book = _book(one)
        if one.status == "reading" and one.started_on:
            book["days_so_far"] = (today - one.started_on).days + 1
        books.append(book)
    return {"books": books, "count": len(books)}


class GetCurrentlyReading(BaseModel):
    pass


async def get_currently_reading(
    connection: AsyncConnection, arguments: GetCurrentlyReading
) -> dict[str, Any]:
    found = await library.books(connection, "reading")
    today = library.today()
    return {
        "reading": [
            {**_book(one), "days_so_far": (today - one.started_on).days + 1}
            for one in found
            if one.started_on
        ]
    }


class GetReadingStats(BaseModel):
    group_by: stats.GroupBy | None = Field(
        default=None,
        description="Sin él, el resumen del año como en la app: libros, páginas, objetivo, "
        "páginas al día, temáticas, autores y lo más largo y lo más rápido.",
    )
    year: int | None = Field(default=None, ge=1900, le=2200, description="Por defecto, este.")


async def get_reading_stats(
    connection: AsyncConnection, arguments: GetReadingStats
) -> dict[str, Any]:
    if arguments.group_by is not None:
        groups = await stats.grouped(connection, arguments.group_by, arguments.year)
        return {
            "group_by": arguments.group_by,
            "year": arguments.year,
            "groups": [group.model_dump() for group in groups],
        }
    found = await stats.year_stats(connection, arguments.year)
    summary = found.model_dump(exclude={"days", "years"})
    return {
        **summary,
        "pages_per_day_note": "estimación: las páginas de cada libro repartidas entre su inicio "
        "y su fin",
    }


class AddBook(BaseModel):
    isbn: str | None = Field(
        default=None, description="ISBN-10 o ISBN-13, con o sin guiones. Si se sabe, mejor."
    )
    title: str | None = Field(default=None, max_length=300)
    authors: list[str] = Field(default_factory=list, max_length=10)
    status: Status = "want"
    started_on: date | None = None
    finished_on: date | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    format: Format = "paper"
    genre: Genre = "other"
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _isbn_or_title(self) -> AddBook:
        if not self.isbn and not (self.title and self.title.strip()):
            raise ValueError("hace falta el ISBN o el título")
        if self.isbn and isbn.to_isbn13(self.isbn) is None:
            raise ValueError(f"«{self.isbn}» no es un ISBN válido")
        return self


def _reading(**fields: Any) -> library.ReadingIn:
    try:
        return library.ReadingIn(**fields)
    except ValueError as error:
        raise library.Conflict(library._first_message(error)) from error


async def add_book(
    connection: AsyncConnection, arguments: AddBook, client: Any = None
) -> dict[str, Any]:
    reading = _reading(
        status=arguments.status,
        started_on=arguments.started_on,
        finished_on=arguments.finished_on,
        rating=arguments.rating,
        format=arguments.format,
        genre=arguments.genre,
        note=arguments.note,
    )
    fallback = library.EditionIn(
        title=arguments.title or (arguments.isbn or ""), authors=arguments.authors
    )
    if arguments.isbn:
        wanted = isbn.to_isbn13(arguments.isbn) or ""
        added = await library.add_by_isbn(connection, client, wanted, fallback, reading)
    else:
        request = library.ManualBookIn(edition=fallback, reading=reading)
        added = await library.add_manual(connection, request, source="tool")
    return {
        "added": _book(added),
        "resolved": added.edition == "catalog",
        "note": None
        if added.edition == "catalog"
        else "Guardado sin resolver: su edición y su portada se eligen en la app.",
    }


class StartReading(BaseModel):
    book_id: UUID = Field(description="El `book_id` de find_books.")
    on: date | None = Field(default=None, description="Por defecto, hoy.")


async def start_reading(connection: AsyncConnection, arguments: StartReading) -> dict[str, Any]:
    found = await library.start(
        connection, str(arguments.book_id), library.StartIn(on=arguments.on)
    )
    return {"book": _book(found)}


class FinishReading(BaseModel):
    book_id: UUID = Field(description="El `book_id` de find_books.")
    on: date | None = Field(default=None, description="Por defecto, hoy.")
    rating: float | None = Field(default=None, ge=0, le=5)


async def finish_reading(connection: AsyncConnection, arguments: FinishReading) -> dict[str, Any]:
    request = library.FinishIn(on=arguments.on, rating=arguments.rating)
    found = await library.finish(connection, str(arguments.book_id), request)
    return {"book": _book(found)}


class RateBook(BaseModel):
    book_id: UUID = Field(description="El `book_id` de find_books.")
    rating: float = Field(ge=0, le=5, description="De 0 a 5, de medio en medio punto.")


async def rate_book(connection: AsyncConnection, arguments: RateBook) -> dict[str, Any]:
    found = await library.rate(connection, str(arguments.book_id), arguments.rating)
    return {"book": _book(found)}


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]
    asks_the_hub: bool = False


TOOLS: dict[str, Tool] = {
    "find_books": Tool(FindBooks, find_books),
    "get_currently_reading": Tool(GetCurrentlyReading, get_currently_reading),
    "get_reading_stats": Tool(GetReadingStats, get_reading_stats),
    "add_book": Tool(AddBook, add_book, asks_the_hub=True),
    "start_reading": Tool(StartReading, start_reading),
    "finish_reading": Tool(FinishReading, finish_reading),
    "rate_book": Tool(RateBook, rate_book),
}
