from __future__ import annotations

import json
from datetime import date, datetime
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from library import isbn

MADRID = ZoneInfo("Europe/Madrid")

Status = Literal["want", "reading", "read", "abandoned"]
Format = Literal["paper", "ebook", "audio"]
Genre = Literal[
    "novel",
    "essay",
    "history",
    "science",
    "biography",
    "business",
    "fantasy_scifi",
    "crime",
    "poetry",
    "comic",
    "other",
]

GENRES: dict[str, str] = {
    "novel": "Novela",
    "essay": "Ensayo",
    "history": "Historia",
    "science": "Ciencia",
    "biography": "Biografía",
    "business": "Negocio",
    "fantasy_scifi": "Fantasía y ciencia ficción",
    "crime": "Policiaca",
    "poetry": "Poesía",
    "comic": "Cómic",
    "other": "Otros",
}


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def today() -> date:
    return datetime.now(MADRID).date()


class GenreOut(BaseModel):
    id: str
    name: str


class Book(BaseModel):
    id: str
    edition: Literal["catalog", "manual"]
    edition_id: str
    title: str
    subtitle: str | None
    authors: list[str]
    pages: int | None
    language: str | None
    year: int | None
    isbn13: str | None
    has_cover: bool
    status: Status
    started_on: date | None
    finished_on: date | None
    rating: float | None
    format: Format
    genre: Genre
    note: str | None
    source: str
    days: int | None


BOOKS = """
    select r.id, r.status, r.started_on, r.finished_on, r.rating, r.format, r.genre, r.note,
           r.source,
           case when r.edition_id is null then 'manual' else 'catalog' end as edition,
           coalesce(r.edition_id, r.manual_edition_id) as edition_id,
           coalesce(e.title, m.title) as title,
           coalesce(e.subtitle, m.subtitle) as subtitle,
           coalesce(e.authors, m.authors) as authors,
           coalesce(e.pages, m.pages) as pages,
           coalesce(e.language, m.language) as language,
           coalesce(e.year, m.year) as year,
           coalesce(e.isbn13, m.isbn13) as isbn13,
           coalesce(e.cover_type, m.cover_type) is not null as has_cover
    from library.library_reading r
    left join library.library_edition e on e.id = r.edition_id
    left join library.library_manual_edition m on m.id = r.manual_edition_id
"""

ORDER = """
    order by case r.status when 'reading' then 0 when 'read' then 1 when 'abandoned' then 1
                           else 2 end,
             coalesce(r.finished_on, r.started_on) desc nulls last,
             r.created_at desc
"""


def _book(row) -> Book:
    days = None
    if row.started_on and row.finished_on:
        days = (row.finished_on - row.started_on).days + 1
    return Book(
        id=str(row.id),
        edition=row.edition,
        edition_id=str(row.edition_id),
        title=row.title,
        subtitle=row.subtitle,
        authors=list(row.authors),
        pages=row.pages,
        language=row.language,
        year=row.year,
        isbn13=row.isbn13,
        has_cover=row.has_cover,
        status=row.status,
        started_on=row.started_on,
        finished_on=row.finished_on,
        rating=float(row.rating) if row.rating is not None else None,
        format=row.format,
        genre=row.genre,
        note=row.note,
        source=row.source,
        days=days,
    )


def genres() -> list[GenreOut]:
    return [GenreOut(id=key, name=name) for key, name in GENRES.items()]


async def books(
    connection: AsyncConnection, status: Status | None = None, year: int | None = None
) -> list[Book]:
    where, params = [], {}
    if status is not None:
        where.append("r.status = :status")
        params["status"] = status
    if year is not None:
        where.append("extract(year from coalesce(r.finished_on, r.started_on)) = :year")
        params["year"] = year
    clause = f"where {' and '.join(where)}" if where else ""
    rows = (await connection.execute(text(f"{BOOKS} {clause} {ORDER}"), params)).all()
    return [_book(row) for row in rows]


async def book(connection: AsyncConnection, reading_id: str) -> Book:
    row = (
        await connection.execute(
            text(f"{BOOKS} where r.id = cast(:id as uuid)"), {"id": reading_id}
        )
    ).one_or_none()
    if row is None:
        raise NotFound(f"el libro {reading_id}")
    return _book(row)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class ReadingIn(BaseModel):
    status: Status
    started_on: date | None = None
    finished_on: date | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    format: Format = "paper"
    genre: Genre = "other"
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("rating")
    @classmethod
    def _half_points(cls, value: float | None) -> float | None:
        if value is not None and value * 2 != int(value * 2):
            raise ValueError("la valoración va de medio en medio punto")
        return value

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _dates_say_the_status(self) -> Self:
        started, finished = self.started_on, self.finished_on
        if self.status == "want" and (started or finished):
            raise ValueError("un libro que quieres leer todavía no tiene fechas")
        if self.status == "reading" and (started is None or finished is not None):
            raise ValueError("leyendo es con fecha de inicio y sin fecha de fin")
        if self.status == "read" and (started is None or finished is None):
            raise ValueError("leído es con fecha de inicio y de fin")
        if self.status == "abandoned" and started is None:
            raise ValueError("para dejarlo hay que haberlo empezado: falta la fecha de inicio")
        if started and finished and finished < started:
            raise ValueError("la fecha de fin es anterior a la de inicio")
        future = today()
        if (started and started > future) or (finished and finished > future):
            raise ValueError("las fechas no pueden ser de después de hoy")
        return self


class EditionIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subtitle: str | None = Field(default=None, max_length=300)
    authors: list[str] = Field(default_factory=list, max_length=10)
    pages: int | None = Field(default=None, gt=0, lt=20000)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    year: int | None = Field(default=None, ge=1400, le=2200)
    isbn: str | None = None

    @field_validator("title", "subtitle")
    @classmethod
    def _spaces(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("authors")
    @classmethod
    def _authors(cls, value: list[str]) -> list[str]:
        return [name for name in (_clean(one) for one in value) if name]

    @field_validator("isbn")
    @classmethod
    def _isbn(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normal = isbn.to_isbn13(value)
        if normal is None:
            raise ValueError(f"«{value}» no es un ISBN válido")
        return normal

    @model_validator(mode="after")
    def _has_title(self) -> Self:
        if not self.title:
            raise ValueError("falta el título")
        return self


class ManualBookIn(BaseModel):
    edition: EditionIn
    reading: ReadingIn


INSERT_MANUAL = text("""
    insert into library.library_manual_edition
        (title, subtitle, authors, pages, language, year, isbn13)
    values (:title, :subtitle, :authors, :pages, :language, :year, :isbn13)
    returning id
""")

INSERT_READING = text("""
    insert into library.library_reading
        (edition_id, manual_edition_id, status, started_on, finished_on, rating, format, genre,
         note, source)
    values (cast(:edition_id as uuid), cast(:manual_edition_id as uuid), :status, :started_on,
            :finished_on, :rating, :format, :genre, :note, :source)
    returning id
""")

UPDATE_READING = text("""
    update library.library_reading
    set status = :status, started_on = :started_on, finished_on = :finished_on, rating = :rating,
        format = :format, genre = :genre, note = :note, updated_at = now()
    where id = cast(:id as uuid)
    returning id
""")

UPDATE_MANUAL = text("""
    update library.library_manual_edition
    set title = :title, subtitle = :subtitle, authors = :authors, pages = :pages,
        language = :language, year = :year, isbn13 = :isbn13
    where id = (select manual_edition_id from library.library_reading where id = cast(:id as uuid))
    returning id
""")

ENQUEUE = text("""
    insert into library.library_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :dedup)
    on conflict do nothing
""")


def _reading_params(reading: ReadingIn) -> dict:
    return {
        "status": reading.status,
        "started_on": reading.started_on,
        "finished_on": reading.finished_on,
        "rating": reading.rating,
        "format": reading.format,
        "genre": reading.genre,
        "note": reading.note,
    }


def _edition_params(edition: EditionIn) -> dict:
    return {
        "title": edition.title,
        "subtitle": edition.subtitle,
        "authors": edition.authors,
        "pages": edition.pages,
        "language": edition.language,
        "year": edition.year,
        "isbn13": edition.isbn,
    }


async def _announce(connection: AsyncConnection, found: Book) -> None:
    if found.status != "read" or found.finished_on is None:
        return
    payload = {
        "reading_id": found.id,
        "title": found.title,
        "authors": found.authors,
        "pages": found.pages,
        "genre": found.genre,
        "format": found.format,
        "started_on": found.started_on.isoformat() if found.started_on else None,
        "finished_on": found.finished_on.isoformat(),
        "rating": found.rating,
    }
    await connection.execute(
        ENQUEUE,
        {
            "type": "library.reading_finished",
            "payload": json.dumps(payload),
            "dedup": f"reading_finished:{found.id}:{found.finished_on.isoformat()}",
        },
    )


async def add_manual(
    connection: AsyncConnection, request: ManualBookIn, source: str = "app"
) -> Book:
    edition = (await connection.execute(INSERT_MANUAL, _edition_params(request.edition))).one()
    reading = (
        await connection.execute(
            INSERT_READING,
            {
                "edition_id": None,
                "manual_edition_id": str(edition.id),
                "source": source,
                **_reading_params(request.reading),
            },
        )
    ).one()
    found = await book(connection, str(reading.id))
    await _announce(connection, found)
    return found


async def update_reading(connection: AsyncConnection, reading_id: str, request: ReadingIn) -> Book:
    updated = (
        await connection.execute(UPDATE_READING, {"id": reading_id, **_reading_params(request)})
    ).one_or_none()
    if updated is None:
        raise NotFound(f"el libro {reading_id}")
    found = await book(connection, reading_id)
    await _announce(connection, found)
    return found


async def update_edition(connection: AsyncConnection, reading_id: str, request: EditionIn) -> Book:
    current = await book(connection, reading_id)
    if current.edition != "manual":
        raise Conflict("los datos de un libro del catálogo vienen de su fuente y no se editan")
    await connection.execute(UPDATE_MANUAL, {"id": reading_id, **_edition_params(request)})
    return await book(connection, reading_id)


class StartIn(BaseModel):
    on: date | None = None


class FinishIn(BaseModel):
    on: date | None = None
    rating: float | None = Field(default=None, ge=0, le=5)


def _as_reading(current: Book, **changes) -> ReadingIn:
    fields = {
        "status": current.status,
        "started_on": current.started_on,
        "finished_on": current.finished_on,
        "rating": current.rating,
        "format": current.format,
        "genre": current.genre,
        "note": current.note,
        **changes,
    }
    try:
        return ReadingIn(**fields)
    except ValueError as error:
        raise Conflict(_first_message(error)) from error


def _first_message(error: ValueError) -> str:
    errors = getattr(error, "errors", None)
    if callable(errors):
        found = errors()
        if found:
            return str(found[0]["msg"]).removeprefix("Value error, ")
    return str(error)


async def start(connection: AsyncConnection, reading_id: str, request: StartIn) -> Book:
    current = await book(connection, reading_id)
    if current.status in ("read", "abandoned"):
        raise Conflict("ya lo terminaste: para releerlo, apúntalo otra vez")
    reading = _as_reading(
        current, status="reading", started_on=request.on or today(), finished_on=None
    )
    return await update_reading(connection, reading_id, reading)


async def rate(connection: AsyncConnection, reading_id: str, rating: float) -> Book:
    current = await book(connection, reading_id)
    return await update_reading(connection, reading_id, _as_reading(current, rating=rating))


async def finish(connection: AsyncConnection, reading_id: str, request: FinishIn) -> Book:
    current = await book(connection, reading_id)
    if current.started_on is None:
        raise Conflict("falta cuándo lo empezaste")
    changes: dict = {"status": "read", "finished_on": request.on or today()}
    if request.rating is not None:
        changes["rating"] = request.rating
    return await update_reading(connection, reading_id, _as_reading(current, **changes))


class Candidate(BaseModel):
    source: Literal["openlibrary", "google_books"]
    source_ref: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    subtitle: str | None = Field(default=None, max_length=300)
    authors: list[str] = Field(default_factory=list, max_length=20)
    isbn13: str | None = None
    pages: int | None = Field(default=None, gt=0, lt=20000)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2}$")
    year: int | None = Field(default=None, ge=1400, le=2200)
    subjects: list[str] = Field(default_factory=list, max_length=40)
    cover_ref: str | None = Field(default=None, max_length=40)

    @field_validator("isbn13")
    @classmethod
    def _isbn(cls, value: str | None) -> str | None:
        return isbn.to_isbn13(value) if value else None


class CandidateOut(Candidate):
    genre_hint: Genre
    known_id: str | None


class SearchOut(BaseModel):
    candidates: list[CandidateOut]
    failed: list[dict[str, str]]


KNOWN = text("""
    select r.id from library.library_reading r
    join library.library_edition e on e.id = r.edition_id
    where (e.source = :source and e.source_ref = :ref)
       or (cast(:isbn as text) is not null and e.isbn13 = :isbn)
    order by r.created_at desc
    limit 1
""")


async def search(connection: AsyncConnection, query: str, client) -> SearchOut:
    from library import genre, hub

    found = await hub.search(client, query)
    seen: set[str] = set()
    out = []
    for raw in found.get("candidates") or []:
        try:
            candidate = Candidate.model_validate(raw)
        except ValueError:
            continue
        if candidate.isbn13:
            if candidate.isbn13 in seen:
                continue
            seen.add(candidate.isbn13)
        known = await connection.scalar(
            KNOWN,
            {"source": candidate.source, "ref": candidate.source_ref, "isbn": candidate.isbn13},
        )
        out.append(
            CandidateOut(
                **candidate.model_dump(),
                genre_hint=genre.propose(candidate.subjects),
                known_id=str(known) if known else None,
            )
        )
    return SearchOut(candidates=out, failed=list(found.get("failed") or []))


class CatalogBookIn(BaseModel):
    candidate: Candidate
    reading: ReadingIn


FIND_EDITION = text("""
    select id, cover is not null as has_cover from library.library_edition
    where (source = :source and source_ref = :ref)
       or (cast(:isbn as text) is not null and isbn13 = :isbn)
    order by (source = :source and source_ref = :ref) desc
    limit 1
""")

INSERT_EDITION = text("""
    insert into library.library_edition
        (isbn13, title, subtitle, authors, pages, language, year, subjects, cover, cover_type,
         source, source_ref)
    values (:isbn13, :title, :subtitle, :authors, :pages, :language, :year, :subjects, :cover,
            :cover_type, :source, :source_ref)
    returning id
""")

SET_COVER = text("""
    update library.library_edition set cover = :cover, cover_type = :cover_type
    where id = :id and cover is null
""")


async def _edition_for(connection: AsyncConnection, candidate: Candidate, client) -> str:
    from library import hub

    existing = (
        await connection.execute(
            FIND_EDITION,
            {"source": candidate.source, "ref": candidate.source_ref, "isbn": candidate.isbn13},
        )
    ).one_or_none()
    image = None
    if candidate.cover_ref and (existing is None or not existing.has_cover):
        image = await hub.cover(client, candidate.source, candidate.cover_ref)
    if existing is not None:
        if image:
            await connection.execute(
                SET_COVER, {"id": existing.id, "cover": image[0], "cover_type": image[1]}
            )
        return str(existing.id)
    edition_id = (
        await connection.execute(
            INSERT_EDITION,
            {
                "isbn13": candidate.isbn13,
                "title": _clean(candidate.title),
                "subtitle": _clean(candidate.subtitle),
                "authors": [a for a in (_clean(one) for one in candidate.authors) if a],
                "pages": candidate.pages,
                "language": candidate.language,
                "year": candidate.year,
                "subjects": candidate.subjects,
                "cover": image[0] if image else None,
                "cover_type": image[1] if image else None,
                "source": candidate.source,
                "source_ref": candidate.source_ref,
            },
        )
    ).scalar_one()
    return str(edition_id)


async def add_from_catalog(
    connection: AsyncConnection, request: CatalogBookIn, client, source: str = "app"
) -> Book:
    edition_id = await _edition_for(connection, request.candidate, client)
    reading = (
        await connection.execute(
            INSERT_READING,
            {
                "edition_id": edition_id,
                "manual_edition_id": None,
                "source": source,
                **_reading_params(request.reading),
            },
        )
    ).one()
    found = await book(connection, str(reading.id))
    await _announce(connection, found)
    return found


class ResolveIn(BaseModel):
    candidate: Candidate


RESOLVE = text("""
    update library.library_reading
    set edition_id = cast(:edition as uuid), manual_edition_id = null, updated_at = now()
    where id = cast(:id as uuid)
""")


async def resolve(connection: AsyncConnection, reading_id: str, request: ResolveIn, client) -> Book:
    current = await book(connection, reading_id)
    if current.edition != "manual":
        raise Conflict("este libro ya es del catálogo")
    edition_id = await _edition_for(connection, request.candidate, client)
    await connection.execute(RESOLVE, {"id": reading_id, "edition": edition_id})
    return await book(connection, reading_id)


async def add_by_isbn(
    connection: AsyncConnection,
    client,
    wanted: str,
    fallback: EditionIn,
    reading: ReadingIn,
    source: str = "tool",
) -> Book:
    from library import hub

    found = await hub.search(client, wanted)
    for raw in found.get("candidates") or []:
        try:
            candidate = Candidate.model_validate(raw)
        except ValueError:
            continue
        if candidate.isbn13 == wanted:
            request = CatalogBookIn(candidate=candidate, reading=reading)
            return await add_from_catalog(connection, request, client, source)
    edition = fallback.model_copy(update={"isbn": wanted})
    return await add_manual(connection, ManualBookIn(edition=edition, reading=reading), source)


FIND_BOOKS = """
    where (cast(:query as text) is null
           or coalesce(e.title, m.title) ilike :like
           or array_to_string(coalesce(e.authors, m.authors), ' ') ilike :like)
      and (cast(:genre as text) is null or r.genre = :genre)
      and (cast(:status as text) is null or r.status = :status)
      and (cast(:year as integer) is null
           or extract(year from coalesce(r.finished_on, r.started_on)) = :year)
"""


async def find(
    connection: AsyncConnection,
    query: str | None,
    genre: str | None,
    status: str | None,
    year: int | None,
    limit: int,
) -> list[Book]:
    params = {
        "query": query,
        "like": f"%{query}%" if query else None,
        "genre": genre,
        "status": status,
        "year": year,
    }
    rows = (
        await connection.execute(text(f"{BOOKS} {FIND_BOOKS} {ORDER} limit {int(limit)}"), params)
    ).all()
    return [_book(row) for row in rows]


COVER = text("""
    select coalesce(e.cover, m.cover) as cover, coalesce(e.cover_type, m.cover_type) as type,
           coalesce(r.edition_id, r.manual_edition_id) as edition_id
    from library.library_reading r
    left join library.library_edition e on e.id = r.edition_id
    left join library.library_manual_edition m on m.id = r.manual_edition_id
    where r.id = cast(:id as uuid)
""")


async def cover(connection: AsyncConnection, reading_id: str) -> tuple[bytes, str, str]:
    row = (await connection.execute(COVER, {"id": reading_id})).one_or_none()
    if row is None or row.cover is None:
        raise NotFound(f"la portada de {reading_id}")
    return bytes(row.cover), row.type, str(row.edition_id)
