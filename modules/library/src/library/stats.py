from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from library.library import GENRES, today

FORMATS = {"paper": "Papel", "ebook": "Ebook", "audio": "Audio"}
LANGUAGES = {
    "es": "Español",
    "en": "Inglés",
    "eu": "Euskera",
    "ca": "Catalán",
    "gl": "Gallego",
    "fr": "Francés",
    "de": "Alemán",
    "it": "Italiano",
    "pt": "Portugués",
}
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic")

READ = text("""
    select r.id, r.started_on, r.finished_on, r.rating, r.format, r.genre,
           coalesce(e.title, m.title) as title,
           coalesce(e.authors, m.authors) as authors,
           coalesce(e.pages, m.pages) as pages,
           coalesce(e.language, m.language) as language
    from library.library_reading r
    left join library.library_edition e on e.id = r.edition_id
    left join library.library_manual_edition m on m.id = r.manual_edition_id
    where r.status = 'read'
    order by r.finished_on, r.created_at
""")

GOAL = text("select books from library.library_goal where year = :year")


class Share(BaseModel):
    id: str
    name: str
    books: int
    pages: int


class Month(BaseModel):
    month: int
    label: str
    books: int
    pages: int


class Highlight(BaseModel):
    id: str
    title: str
    pages: int | None
    days: int | None


class YearStats(BaseModel):
    year: int
    years: list[int]
    books: int
    pages: int
    goal: int | None
    goal_pace: float | None
    average_rating: float | None
    pages_per_day: float
    months: list[Month]
    days: dict[str, float]
    genres: list[Share]
    formats: list[Share]
    languages: list[Share]
    authors: list[Share]
    ratings: dict[str, int]
    longest: Highlight | None
    fastest: Highlight | None


def _days(row) -> int | None:
    if row.started_on and row.finished_on:
        return (row.finished_on - row.started_on).days + 1
    return None


def spread(rows, year: int) -> dict[str, float]:
    return spread_years(rows, {year})


def spread_years(rows, years: set[int]) -> dict[str, float]:
    days: dict[str, float] = defaultdict(float)
    for row in rows:
        length = _days(row)
        if not row.pages or not length:
            continue
        each = row.pages / length
        for offset in range(length):
            day = row.started_on + timedelta(days=offset)
            if day.year in years:
                days[day.isoformat()] += each
    return {day: round(pages, 1) for day, pages in sorted(days.items())}


def _shares(counts: dict[str, list], names: dict[str, str] | None = None) -> list[Share]:
    shares = [
        Share(
            id=key,
            name=(names or {}).get(key, key),
            books=len(found),
            pages=sum(row.pages or 0 for row in found),
        )
        for key, found in counts.items()
    ]
    return sorted(shares, key=lambda share: (-share.books, -share.pages, share.name))


async def year_stats(connection: AsyncConnection, year: int | None = None) -> YearStats:
    now = today()
    year = year or now.year
    rows = (await connection.execute(READ)).all()
    this_year = [row for row in rows if row.finished_on.year == year]
    goal = await connection.scalar(GOAL, {"year": year})

    months = [
        Month(month=index + 1, label=label, books=0, pages=0) for index, label in enumerate(MONTHS)
    ]
    genres: dict[str, list] = defaultdict(list)
    formats: dict[str, list] = defaultdict(list)
    languages: dict[str, list] = defaultdict(list)
    authors: dict[str, list] = defaultdict(list)
    for row in this_year:
        month = months[row.finished_on.month - 1]
        month.books += 1
        month.pages += row.pages or 0
        genres[row.genre].append(row)
        formats[row.format].append(row)
        languages[row.language or "?"].append(row)
        for author in row.authors:
            authors[author].append(row)

    rated = [float(row.rating) for row in this_year if row.rating is not None]
    ratings = Counter(f"{float(row.rating):g}" for row in this_year if row.rating is not None)
    days = spread(rows, year)
    elapsed = (now - date(year, 1, 1)).days + 1 if year == now.year else _length(year)
    with_pages = [row for row in this_year if row.pages]
    timed = [row for row in this_year if _days(row)]

    pace = None
    if goal and year == now.year:
        pace = round(goal * elapsed / _length(year), 1)
    return YearStats(
        year=year,
        years=sorted({row.finished_on.year for row in rows} | {now.year}, reverse=True),
        books=len(this_year),
        pages=sum(row.pages or 0 for row in this_year),
        goal=goal,
        goal_pace=pace,
        average_rating=round(sum(rated) / len(rated), 2) if rated else None,
        pages_per_day=round(sum(days.values()) / max(elapsed, 1), 1) if elapsed > 0 else 0.0,
        months=months,
        days=days,
        genres=_shares(genres, GENRES),
        formats=_shares(formats, FORMATS),
        languages=_shares(languages, {**LANGUAGES, "?": "Sin idioma"}),
        authors=_shares(authors)[:10],
        ratings={key: ratings[key] for key in sorted(ratings, key=float)},
        longest=_highlight(max(with_pages, key=lambda row: row.pages)) if with_pages else None,
        fastest=_highlight(min(timed, key=_days)) if timed else None,
    )


def _length(year: int) -> int:
    return (date(year + 1, 1, 1) - date(year, 1, 1)).days


def _highlight(row) -> Highlight:
    return Highlight(id=str(row.id), title=row.title, pages=row.pages, days=_days(row))


GroupBy = Literal["year", "month", "genre", "author", "format"]


class Group(BaseModel):
    key: str
    books: int
    pages: int
    average_rating: float | None


async def grouped(connection: AsyncConnection, by: GroupBy, year: int | None) -> list[Group]:
    rows = (await connection.execute(READ)).all()
    if year is not None:
        rows = [row for row in rows if row.finished_on.year == year]
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        if by == "year":
            groups[str(row.finished_on.year)].append(row)
        elif by == "month":
            groups[row.finished_on.strftime("%Y-%m")].append(row)
        elif by == "genre":
            groups[row.genre].append(row)
        elif by == "format":
            groups[row.format].append(row)
        else:
            for author in row.authors or ["(sin autor)"]:
                groups[author].append(row)
    out = []
    for key, found in groups.items():
        rated = [float(row.rating) for row in found if row.rating is not None]
        out.append(
            Group(
                key=key,
                books=len(found),
                pages=sum(row.pages or 0 for row in found),
                average_rating=round(sum(rated) / len(rated), 2) if rated else None,
            )
        )
    if by in ("year", "month"):
        return sorted(out, key=lambda group: group.key)
    return sorted(out, key=lambda group: (-group.books, group.key))


class GoalIn(BaseModel):
    books: int = Field(ge=1, le=1000)


SET_GOAL = text("""
    insert into library.library_goal (year, books) values (:year, :books)
    on conflict (user_id, year) do update set books = excluded.books
""")


async def set_goal(connection: AsyncConnection, year: int, request: GoalIn) -> YearStats:
    await connection.execute(SET_GOAL, {"year": year, "books": request.books})
    return await year_stats(connection, year)
