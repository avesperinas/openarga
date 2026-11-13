from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from outings import demo
from outings.common import today

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("outings_wish", "outings_event", "outings_event_source", "outings_interest")


async def counts() -> dict[str, int]:
    from outings.main import as_app

    async with as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from outings.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from outings.main import as_app

    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            async with as_app() as connection:
                await demo.seed(connection, persona, today())
            seen[persona.key] = await counts()
        finally:
            current_spaces.reset(spaces)
            current_user.reset(token)
    return seen


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first == again
    for person in first.values():
        assert person["outings_wish"] >= 8 and person["outings_event"] >= 8
        assert person["outings_interest"] == 3


async def test_the_seed_covers_eighteen_months_and_shares_with_the_space(schema) -> None:
    from outings.main import as_app

    alex = CAST.people[0]
    token = current_user.set(alex.id)
    spaces = current_spaces.set((CAST.space_id,))
    try:
        async with as_app() as connection:
            await demo.seed(connection, alex, today())
            oldest = await connection.scalar(text("select min(done_at) from outings.outings_wish"))
            shared = await connection.scalar(
                text("select count(*) from outings.outings_wish where space_id = :space"),
                {"space": CAST.space_id},
            )
            saved = await connection.scalar(
                text("select count(*) from outings.outings_wish where event_id is not null")
            )
    finally:
        current_spaces.reset(spaces)
        current_user.reset(token)

    assert (today() - oldest.date()).days > 365
    assert shared == 2 and saved == 1
