from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from library import library
from library.words import say

APP = "library"


def _id(book: library.Book) -> str:
    return f"book:{book.id}"


def _stars(rating: float) -> str:
    whole = int(rating)
    return "★" * whole + ("½" if rating - whole >= 0.5 else "") + f" ({write.trimmed(rating, 1)})"


def _reading(book: library.Book) -> str:
    if book.status == "want":
        return say("reading.want")
    start = book.started_on.isoformat() if book.started_on else None
    if book.status == "reading":
        return say("reading.since", start=start)
    end = book.finished_on.isoformat() if book.finished_on else None
    if book.status == "abandoned":
        return say("reading.abandoned_on" if end else "reading.abandoned", start=start, end=end)
    if book.days:
        plural = "one" if book.days == 1 else "other"
        return say(f"reading.read_days.{plural}", start=start, end=end, days=book.days)
    return say("reading.read", start=start, end=end)


def record(book: library.Book) -> dict[str, Any]:
    genre = say(f"genre.{book.genre}")
    first = " · ".join(
        part
        for part in (
            f"**{', '.join(book.authors)}**" if book.authors else None,
            str(book.year) if book.year else None,
            say("record.pages", pages=write.number(book.pages)) if book.pages else None,
            say(f"format.{book.format}"),
            genre,
        )
        if part
    )
    reading = _reading(book)
    if book.rating is not None:
        reading += f" {_stars(book.rating)}"
    properties: dict[str, Any] = {
        "authors": book.authors,
        "status": say(f"status.{book.status}"),
        "genre": genre.lower(),
        "format": say(f"format.{book.format}").lower(),
    }
    for name, value in (
        ("rating", book.rating),
        ("started", book.started_on.isoformat() if book.started_on else None),
        ("finished", book.finished_on.isoformat() if book.finished_on else None),
        ("days", book.days),
        ("pages", book.pages),
        ("year", book.year),
        ("language", book.language),
        ("isbn", book.isbn13),
    ):
        if value is not None:
            properties[name] = value
    return contracts.record(
        id=_id(book),
        title=book.title,
        kind=say("record.book"),
        href=f"/library/books/{book.id}",
        folder=say("record.books"),
        properties=properties,
        body=write.sections(
            first,
            f"*{book.subtitle}*" if book.subtitle else None,
            f"## {say('record.reading')}\n\n{reading}",
            f"## {say('record.note')}\n\n{book.note}" if book.note else None,
        ),
    )


def days(books: list[library.Book]) -> list[dict[str, Any]]:
    lines: dict[date, list[str]] = defaultdict(list)
    for book in sorted(books, key=lambda one: one.title.casefold()):
        shown = write.link(APP, _id(book), book.title)
        if book.started_on is not None:
            lines[book.started_on].append(f"- {say('record.started', book=shown)}")
        if book.finished_on is not None:
            key = "record.abandoned" if book.status == "abandoned" else "record.finished"
            rating = f" · {_stars(book.rating)}" if book.rating is not None else ""
            lines[book.finished_on].append(f"- {say(key, book=shown)}{rating}")
    return [
        contracts.record(
            id=f"day:{day.isoformat()}",
            title=say("record.readings"),
            kind=say("record.day"),
            href="/library/",
            day=day,
            body="\n".join(found),
        )
        for day, found in sorted(lines.items())
    ]


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    books = await library.books(connection)
    return [record(book) for book in books] + days(books)
