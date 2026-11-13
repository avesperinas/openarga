from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-0000001b7a1b")
MONTHS = 18

EDITION = text("""
    insert into library.library_manual_edition (id, title, authors, pages, language, year)
    values (:id, :title, :authors, :pages, :language, :year)
    on conflict (id) do nothing
""")

READING = text("""
    insert into library.library_reading
        (id, manual_edition_id, status, started_on, finished_on, rating, format, genre, note)
    values (:id, :edition, :status, :started_on, :finished_on, :rating, :format, :genre, :note)
    on conflict (id) do nothing
""")

GOAL = text("""
    insert into library.library_goal (year, books) values (:year, :books)
    on conflict (user_id, year) do nothing
""")

WORDS = (
    "Silent", "Northern", "Glass", "Paper", "Hidden", "Long", "Salt", "Winter", "Iron",
    "Quiet", "Copper", "Distant", "Last", "Bright", "Hollow", "Open",
)  # fmt: skip
THINGS = (
    "Harbour", "Orchard", "Archive", "Garden", "River", "Lighthouse", "Library", "Mountain",
    "Theory", "Map", "Kitchen", "Machine", "Island", "Season", "Letters", "Bridge",
)  # fmt: skip
AUTHORS = (
    "Ada Synthetic", "Ben Example", "Clara Placeholder", "Dev Sample", "Eli Fictional",
    "Flor Imaginary", "Gus Invented", "Hana Madeup",
)  # fmt: skip
GENRES = ("novel", "essay", "history", "science", "crime", "fantasy_scifi", "biography", "poetry")
FORMATS = ("paper", "paper", "ebook", "audio")


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.key}:{key}")


def _books(persona: Persona, today: date) -> list[dict]:
    offset = 0 if persona.key == "alex" else 5
    found = []
    for n in range(MONTHS * 2):
        index = n + offset
        finished = today - timedelta(days=5 + n * 15 + index % 4)
        days = 6 + (index * 7) % 25
        found.append(
            {
                "key": f"read-{n}",
                "status": "abandoned" if n == 7 else "read",
                "started_on": finished - timedelta(days=days - 1),
                "finished_on": finished,
                "rating": None if n == 7 else 2.5 + (index % 6) * 0.5,
                "index": index,
            }
        )
    found.append(
        {
            "key": "now",
            "status": "reading",
            "started_on": today - timedelta(days=3),
            "finished_on": None,
            "rating": None,
            "index": 40 + offset,
        }
    )
    for n in range(3):
        found.append(
            {
                "key": f"want-{n}",
                "status": "want",
                "started_on": None,
                "finished_on": None,
                "rating": None,
                "index": 50 + n + offset,
            }
        )
    return found


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    for one in _books(persona, today):
        index = one["index"]
        edition = _id(persona, f"edition-{one['key']}")
        await connection.execute(
            EDITION,
            {
                "id": edition,
                "title": f"The {WORDS[index % len(WORDS)]} {THINGS[(index * 3) % len(THINGS)]}",
                "authors": [AUTHORS[index % len(AUTHORS)]],
                "pages": 140 + (index * 37) % 520,
                "language": "es" if persona.locale == "es" and index % 3 else "en",
                "year": 1950 + (index * 11) % 75,
            },
        )
        await connection.execute(
            READING,
            {
                "id": _id(persona, one["key"]),
                "edition": edition,
                "status": one["status"],
                "started_on": one["started_on"],
                "finished_on": one["finished_on"],
                "rating": one["rating"],
                "format": FORMATS[index % len(FORMATS)],
                "genre": GENRES[index % len(GENRES)],
                "note": "Worth rereading." if one["rating"] and one["rating"] >= 4.5 else None,
            },
        )
    for year, books in ((today.year, 24), (today.year - 1, 20)):
        await connection.execute(GOAL, {"year": year, "books": books})
