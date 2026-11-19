from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona

NAMESPACE = UUID("0b7c0de5-0000-4000-8000-0000001b7a1b")
SPAN = 530

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

ALEX_SHELF = (
    (
        "The Cartographer of Salt Marshes",
        "Marian Holloway",
        "novel",
        412,
        2019,
        "en",
        4.5,
        "paper",
        "Quiet, patient, and the ending lands.",
    ),
    ("A Tide Without a Moon", "Idris Calder", "fantasy_scifi", 538, 2021, "en", 4.0, "ebook", None),
    ("Counting the Hours", "Noor Vasquez-Hale", "science", 296, 2020, "en", 3.5, "paper", None),
    (
        "The Long Winter of 1741",
        "Jonas Albrecht",
        "history",
        624,
        2016,
        "en",
        4.5,
        "paper",
        "The chapter on the grain trade is superb.",
    ),
    ("Signal and Static", "Priya Raman-Cole", "science", 348, 2022, "en", 4.0, "audio", None),
    (
        "Ashes of the Brass Republic",
        "Tomas Veyra",
        "fantasy_scifi",
        702,
        2018,
        "en",
        3.0,
        "ebook",
        None,
    ),
    (
        "What the River Kept",
        "Hugo Marechal",
        "novel",
        264,
        2015,
        "en",
        5.0,
        "paper",
        "Rereading this one every few years.",
    ),
    (
        "Letters from a Slow Train",
        "Elena Sorokina-Park",
        "essay",
        188,
        2023,
        "en",
        4.0,
        "paper",
        None,
    ),
    ("The Quiet Algorithm", "Oona Lindqvist", "science", 332, 2024, "en", 3.5, "ebook", None),
    ("Nine Roads to Valparaiso", "Mateo Brandt", "crime", 376, 2017, "en", 3.5, "paper", None),
    ("An Honest Map of the Moon", "Idris Calder", "essay", 212, 2020, "en", 4.0, "paper", None),
    ("Harbour Lights", "Clara Whitcombe", "novel", 322, 2012, "en", 3.0, "paper", None),
    (
        "The Architecture of Memory",
        "Leon Hartmann",
        "science",
        410,
        2014,
        "en",
        4.5,
        "audio",
        "Changed how I take notes.",
    ),
    ("Blood on the Orchard Wall", "Mateo Brandt", "crime", 344, 2019, "en", 3.5, "ebook", None),
    ("The Lantern Year", "Marian Holloway", "novel", 458, 2022, "en", 4.0, "paper", None),
    ("Steel, Salt and Sail", "Jonas Albrecht", "history", 566, 2018, "en", 4.0, "paper", None),
    (
        "The Unfinished Equation",
        "Priya Raman-Cole",
        "biography",
        380,
        2021,
        "en",
        4.5,
        "audio",
        "A scientist's life told without hero worship.",
    ),
    ("Small Hours in Lisbon", "Ines Carvalho", "poetry", 96, 2020, "en", 4.0, "paper", None),
    (
        "Orbit of the Last Station",
        "Tomas Veyra",
        "fantasy_scifi",
        610,
        2023,
        "en",
        4.5,
        "ebook",
        "Best space opera in years.",
    ),
    ("Field Notes on Boredom", "Elena Sorokina-Park", "essay", 164, 2021, "en", 3.0, "paper", None),
    (
        "The Ledger of Kings",
        "Leon Hartmann",
        "history",
        740,
        2013,
        "en",
        None,
        "paper",
        "Too dense. Dropped at chapter nine.",
    ),
    ("The Winter Garden Murders", "Clara Whitcombe", "crime", 298, 2016, "en", 3.0, "paper", None),
    ("How Bridges Think", "Oona Lindqvist", "science", 270, 2019, "en", 4.0, "paper", None),
    ("Where the Compass Fails", "Mateo Brandt", "novel", 356, 2024, "en", 3.5, "audio", None),
    ("The Copper Hours", "Noor Vasquez-Hale", "novel", 402, 2020, "en", 4.0, "paper", None),
    (
        "Reasons to Stay Offline",
        "Elena Sorokina-Park",
        "essay",
        154,
        2024,
        "en",
        4.0,
        "ebook",
        "Short, sharp and a little smug.",
    ),
    ("The Salt Road", "Hugo Marechal", "history", 498, 2017, "en", 4.0, "paper", None),
    (
        "Terminal Velocity of Rain",
        "Idris Calder",
        "fantasy_scifi",
        486,
        2022,
        "en",
        3.5,
        "ebook",
        None,
    ),
    (
        "Portrait of a Quiet Engineer",
        "Ines Carvalho",
        "biography",
        330,
        2022,
        "en",
        3.5,
        "paper",
        None,
    ),
    (
        "The Distant Orchard",
        "Marian Holloway",
        "novel",
        378,
        2024,
        "en",
        4.5,
        "paper",
        "Gift for Sam, borrowed back.",
    ),
    ("Maps for Getting Lost", "Jonas Albrecht", "essay", 226, 2018, "en", 3.5, "paper", None),
    ("The Glass Cartel", "Mateo Brandt", "crime", 420, 2025, "en", 3.0, "ebook", None),
    (
        "Statistics for the Stubborn",
        "Leon Hartmann",
        "science",
        352,
        2025,
        "en",
        4.0,
        "paper",
        None,
    ),
    ("The House at Kestrel Point", "Clara Whitcombe", "novel", 334, 2025, "en", 3.5, "audio", None),
    (
        "Chronicle of a Slow Revolution",
        "Tomas Veyra",
        "history",
        588,
        2025,
        "en",
        4.0,
        "paper",
        None,
    ),
    ("The Fourth Bell", "Priya Raman-Cole", "fantasy_scifi", 544, 2025, "en", 4.0, "ebook", None),
    ("Lessons in Deep Work", "Oona Lindqvist", "science", 300, 2026, "en", 3.5, "audio", None),
)

ALEX_NOW = (
    ("The Winter Observatory", "Idris Calder", "fantasy_scifi", 480, 2026, "en", "ebook"),
    ("A Grammar of Mountains", "Noor Vasquez-Hale", "essay", 240, 2025, "en", "paper"),
)

ALEX_WANT = (
    ("The Ninth Meridian", "Hugo Marechal", "novel", 430, 2026, "en"),
    ("Cold Storage Diaries", "Ines Carvalho", "crime", 312, 2026, "en"),
    ("The Physics of Everyday Rain", "Priya Raman-Cole", "science", 286, 2026, "en"),
    ("A Brief History of Salt", "Jonas Albrecht", "history", 344, 2024, "en"),
    ("Night Shift at the Observatory", "Elena Sorokina-Park", "novel", 260, 2026, "en"),
)

SAM_SHELF = (
    (
        "The House of Cypress Trees",
        "Lucia Ferran",
        "novel",
        344,
        2018,
        "en",
        4.5,
        "paper",
        "Reminded me of my grandmother.",
    ),
    (
        "The Cloud Cartographer",
        "Rafael Idoate",
        "fantasy_scifi",
        402,
        2020,
        "en",
        4.0,
        "ebook",
        None,
    ),
    (
        "Stories for After Dinner",
        "Marta Etxeberria",
        "novel",
        188,
        2016,
        "en",
        3.5,
        "paper",
        None,
    ),
    (
        "The Weight of Salt",
        "Irene Larrea",
        "novel",
        296,
        2021,
        "en",
        4.5,
        "paper",
        "A perfect ending.",
    ),
    (
        "A Short History of Valley Wine",
        "Javier Urdiain",
        "history",
        274,
        2015,
        "en",
        3.5,
        "paper",
        None,
    ),
    (
        "Letters from the Northern Coast",
        "Lucia Ferran",
        "essay",
        176,
        2022,
        "en",
        4.0,
        "paper",
        None,
    ),
    ("The Quiet Garden Rules", "Nell Fairbourne", "crime", 322, 2019, "en", 3.0, "ebook", None),
    ("The Last Station Stop", "Pablo Zuazu", "crime", 368, 2017, "en", 3.5, "paper", None),
    (
        "A Science of Ordinary Things",
        "Elisa Montoya",
        "science",
        284,
        2020,
        "en",
        4.0,
        "audio",
        None,
    ),
    (
        "The Children of Winter",
        "Rafael Idoate",
        "fantasy_scifi",
        560,
        2022,
        "en",
        4.0,
        "ebook",
        None,
    ),
    (
        "The Violin Maker's Daughter",
        "Nell Fairbourne",
        "novel",
        412,
        2018,
        "en",
        4.5,
        "paper",
        "Cried on the train.",
    ),
    (
        "Diary of a Librarian",
        "Irene Larrea",
        "biography",
        230,
        2019,
        "en",
        4.0,
        "paper",
        None,
    ),
    (
        "Poems of the River Valley",
        "Marta Etxeberria",
        "poetry",
        88,
        2021,
        "en",
        4.5,
        "paper",
        "To reread in spring.",
    ),
    (
        "The Man Who Counted Stairs",
        "Pablo Zuazu",
        "novel",
        258,
        2014,
        "en",
        3.0,
        "paper",
        None,
    ),
    (
        "Mindful Mornings",
        "Daniel Roscoe",
        "other",
        210,
        2020,
        "en",
        None,
        "ebook",
        "Not for me. Dropped it.",
    ),
    ("Memoirs of a Cook", "Elisa Montoya", "biography", 318, 2017, "en", 4.0, "paper", None),
    (
        "The Biology of Wonder",
        "Elisa Montoya",
        "science",
        340,
        2023,
        "en",
        4.5,
        "audio",
        "Very accessible and beautifully written.",
    ),
    ("Three Summers in Sorrento", "Lucia Ferran", "novel", 364, 2023, "en", 3.5, "paper", None),
    ("Orchids in the Fog", "Javier Urdiain", "crime", 290, 2022, "en", 3.5, "ebook", None),
    ("The Weight of Small Things", "Nell Fairbourne", "essay", 196, 2021, "en", 4.0, "paper", None),
    (
        "Atlas of Villages That No Longer Exist",
        "Rafael Idoate",
        "history",
        450,
        2019,
        "en",
        4.0,
        "paper",
        None,
    ),
    ("Habits That Actually Work", "Daniel Roscoe", "business", 246, 2022, "en", 3.0, "audio", None),
    ("That Month of August", "Irene Larrea", "novel", 312, 2024, "en", 4.0, "paper", None),
    (
        "The Garden of Seasons",
        "Marta Etxeberria",
        "novel",
        270,
        2024,
        "en",
        4.5,
        "paper",
        None,
    ),
    ("The Sunken City", "Pablo Zuazu", "fantasy_scifi", 498, 2024, "en", 3.5, "ebook", None),
    (
        "Cooking With What You Have",
        "Elisa Montoya",
        "other",
        222,
        2023,
        "en",
        4.0,
        "paper",
        "Three recipes already in the recipe book.",
    ),
    ("Summer Clouds", "Lucia Ferran", "novel", 286, 2025, "en", 4.0, "paper", None),
    ("The Time of Cherries", "Javier Urdiain", "history", 402, 2025, "en", 3.5, "paper", None),
    ("Small Rooms, Big Lives", "Nell Fairbourne", "biography", 340, 2025, "en", 4.0, "audio", None),
    ("What the Rivers Keep Quiet", "Irene Larrea", "crime", 330, 2025, "en", 4.0, "ebook", None),
    (
        "Essays for Walking",
        "Marta Etxeberria",
        "essay",
        164,
        2025,
        "en",
        4.5,
        "paper",
        "A book to carry in your pocket.",
    ),
    ("A Hundred Days of Rain", "Rafael Idoate", "novel", 376, 2026, "en", 3.5, "paper", None),
    ("Physics for the Curious", "Elisa Montoya", "science", 290, 2026, "en", 4.0, "audio", None),
)

SAM_NOW = (
    ("The Northern Lighthouse", "Lucia Ferran", "novel", 320, 2026, "en", "paper"),
    ("Quiet Hours", "Nell Fairbourne", "essay", 200, 2026, "en", "ebook"),
)

SAM_WANT = (
    ("The Four Seasons of the Forest", "Marta Etxeberria", "essay", 210, 2026, "en"),
    ("The Island of Clocks", "Rafael Idoate", "fantasy_scifi", 430, 2026, "en"),
    ("A Winter in Prague", "Pablo Zuazu", "novel", 300, 2025, "en"),
    ("Mountain Notebook", "Javier Urdiain", "other", 180, 2024, "en"),
    ("Anatomy of a Summer", "Irene Larrea", "crime", 340, 2026, "en"),
)

SHELVES = {
    "alex": (ALEX_SHELF, ALEX_NOW, ALEX_WANT),
    "sam": (SAM_SHELF, SAM_NOW, SAM_WANT),
}


def _id(persona: Persona, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{persona.key}:{key}")


def _days(index: int, total: int) -> tuple[int, int]:
    finished = SPAN - round((index + 1) * (SPAN - 6) / total)
    length = 5 + (index * 7) % 22
    return finished, length


async def _add(
    connection: AsyncConnection,
    persona: Persona,
    key: str,
    book: tuple,
    status: str,
    started: date | None,
    finished: date | None,
    rating: float | None,
    fmt: str,
    note: str | None,
) -> None:
    title, author, genre, pages, year, language = book[:6]
    edition = _id(persona, f"edition-{key}")
    await connection.execute(
        EDITION,
        {
            "id": edition,
            "title": title,
            "authors": [author],
            "pages": pages,
            "language": language,
            "year": year,
        },
    )
    await connection.execute(
        READING,
        {
            "id": _id(persona, key),
            "edition": edition,
            "status": status,
            "started_on": started,
            "finished_on": finished,
            "rating": rating,
            "format": fmt,
            "genre": genre,
            "note": note,
        },
    )


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    shelf, now, want = SHELVES[persona.key]
    for index, book in enumerate(shelf):
        back, length = _days(index, len(shelf))
        finished = today - timedelta(days=back)
        rating, fmt, note = book[6], book[7], book[8]
        await _add(
            connection,
            persona,
            f"read-{index}",
            book,
            "abandoned" if rating is None else "read",
            finished - timedelta(days=length),
            finished,
            rating,
            fmt,
            note,
        )
    for index, book in enumerate(now):
        started = today - timedelta(days=4 + index * 12)
        await _add(
            connection, persona, f"now-{index}", book, "reading", started, None, None, book[6], None
        )
    for index, book in enumerate(want):
        await _add(
            connection, persona, f"want-{index}", book, "want", None, None, None, "paper", None
        )
    for year, books in ((today.year, 24), (today.year - 1, 20)):
        await connection.execute(GOAL, {"year": year, "books": books})
