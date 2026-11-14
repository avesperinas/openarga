from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona
from notebook import notes

REVIEW = "next_review"
JOURNAL = "Journal"


def _notes(persona: Persona, today: date) -> list[tuple[str, str, str]]:
    soon, late = today + timedelta(days=3), today - timedelta(days=2)
    if persona.key == "alex":
        return [
            (
                "",
                "Ideas",
                "- Learn to bake bread\n- A weekend in the mountains\n- [[Reading list]]\n",
            ),
            ("", "Reading list", "Books to look for, see [[Ideas]].\n\n- An invented novel\n"),
            (
                "Study/German",
                "Dative prepositions",
                f"---\n{REVIEW}: {late.isoformat()}\ntags: [german]\n---\n"
                "# Dative prepositions\n\naus, bei, mit, nach, seit, von, zu.\n\n"
                "See [[Accusative prepositions]].\n",
            ),
            (
                "Study/German",
                "Accusative prepositions",
                f"---\n{REVIEW}: {soon.isoformat()}\ntags: [german]\n---\n"
                "# Accusative prepositions\n\ndurch, für, gegen, ohne, um.\n\n"
                "See [[Dative prepositions]].\n",
            ),
            ("Projects/Home", "Kitchen shelves", "- Measure the wall\n- Buy brackets\n"),
        ]
    return [
        ("", "Ideas", "- Try a new pasta shape\n- [[Garden plan]]\n"),
        (
            "Projects",
            "Garden plan",
            f"---\n{REVIEW}: {late.isoformat()}\n---\n"
            "# Garden plan\n\nTomatoes, basil and beans.\n",
        ),
        ("Projects", "Bike repair", "Chain, brakes and the back light. See [[Ideas]].\n"),
    ]


def _days(persona: Persona, today: date) -> list[tuple[date, str]]:
    lines = (
        ["Long walk after work.", "Read for an hour.", "Called the family."]
        if persona.key == "alex"
        else ["Swimming in the morning.", "Cooked for friends.", "Quiet day at home."]
    )
    return [(today - timedelta(days=n), f"- {lines[n % len(lines)]}\n") for n in range(1, 8)]


async def _create(connection: AsyncConnection, folder: str, title: str, content: str) -> None:
    try:
        await notes.create(connection, folder, title, content)
    except notes.Conflict:
        return


async def seed(connection: AsyncConnection, persona: Persona, today: date) -> None:
    await notes.save_settings(
        connection, notes.Settings(daily_folder=JOURNAL, review_property=REVIEW)
    )
    for folder, title, content in _notes(persona, today):
        await _create(connection, folder, title, content)
    for day, content in _days(persona, today):
        await _create(connection, JOURNAL, day.isoformat(), content)
