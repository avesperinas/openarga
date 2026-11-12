from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from library import library

APP = "library"
STATUS = {"want": "quiero leer", "reading": "leyendo", "read": "leído", "abandoned": "abandonado"}
FORMAT = {"paper": "papel", "ebook": "ebook", "audio": "audiolibro"}


def _id(book: library.Book) -> str:
    return f"book:{book.id}"


def _stars(rating: float) -> str:
    whole = int(rating)
    return "★" * whole + ("½" if rating - whole >= 0.5 else "") + f" ({write.trimmed(rating, 1)})"


def _reading(book: library.Book) -> str:
    if book.status == "want":
        return "Quieres leerlo."
    start = write.long_date(book.started_on) if book.started_on else None
    if book.status == "reading":
        return f"Leyéndolo desde el {start}."
    end = write.long_date(book.finished_on) if book.finished_on else None
    if book.status == "abandoned":
        return f"Empezado el {start} y abandonado" + (f" el {end}." if end else ".")
    days = f", en {book.days} {'día' if book.days == 1 else 'días'}" if book.days else ""
    return f"Leído del {start} al {end}{days}."


def ficha(book: library.Book) -> dict[str, Any]:
    first = " · ".join(
        part
        for part in (
            f"**{', '.join(book.authors)}**" if book.authors else None,
            str(book.year) if book.year else None,
            f"{write.number(book.pages)} páginas" if book.pages else None,
            FORMAT[book.format],
            library.GENRES[book.genre],
        )
        if part
    )
    reading = _reading(book)
    if book.rating is not None:
        reading += f" {_stars(book.rating)}"
    properties: dict[str, Any] = {
        "autores": book.authors,
        "estado": STATUS[book.status],
        "genero": library.GENRES[book.genre].lower(),
        "formato": FORMAT[book.format],
    }
    for name, value in (
        ("valoracion", book.rating),
        ("empezado", book.started_on.isoformat() if book.started_on else None),
        ("terminado", book.finished_on.isoformat() if book.finished_on else None),
        ("dias", book.days),
        ("paginas", book.pages),
        ("anio", book.year),
        ("idioma", book.language),
        ("isbn", book.isbn13),
    ):
        if value is not None:
            properties[name] = value
    return contracts.record(
        id=_id(book),
        title=book.title,
        kind="Libro",
        href=f"/library/libro/{book.id}",
        folder="Libros",
        properties=properties,
        body=write.sections(
            first,
            f"*{book.subtitle}*" if book.subtitle else None,
            f"## Lectura\n\n{reading}",
            f"## Nota\n\n{book.note}" if book.note else None,
        ),
    )


def days(books: list[library.Book]) -> list[dict[str, Any]]:
    lines: dict[date, list[str]] = defaultdict(list)
    for book in sorted(books, key=lambda one: one.title.casefold()):
        shown = write.link(APP, _id(book), book.title)
        if book.started_on is not None:
            lines[book.started_on].append(f"- Empezaste {shown}")
        if book.finished_on is not None:
            verb = "Abandonaste" if book.status == "abandoned" else "Terminaste"
            rating = f" · {_stars(book.rating)}" if book.rating is not None else ""
            lines[book.finished_on].append(f"- {verb} {shown}{rating}")
    return [
        contracts.record(
            id=f"day:{day.isoformat()}",
            title="Lecturas",
            kind="Día",
            href="/library/",
            day=day,
            body="\n".join(found),
        )
        for day, found in sorted(lines.items())
    ]


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    books = await library.books(connection)
    return [ficha(book) for book in books] + days(books)
