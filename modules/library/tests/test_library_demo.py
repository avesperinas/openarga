from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_user
from library import demo
from library.library import today

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("library_manual_edition", "library_reading", "library_goal")


async def seed_everyone() -> dict[str, dict[str, int]]:
    from library.main import service

    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        try:
            async with service.as_app() as connection:
                await demo.seed(connection, persona, today())
                seen[persona.key] = {
                    table: await connection.scalar(text(f"select count(*) from library.{table}"))
                    for table in TABLES
                }
        finally:
            current_user.reset(token)
    return seen


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first == again
    for person in first.values():
        assert person["library_reading"] == 40 and person["library_goal"] == 2


async def test_the_seed_covers_eighteen_months_and_every_status(schema) -> None:
    from library.main import service

    alex = CAST.people[0]
    token = current_user.set(alex.id)
    try:
        async with service.as_app() as connection:
            await demo.seed(connection, alex, today())
            oldest = await connection.scalar(
                text("select min(finished_on) from library.library_reading")
            )
            statuses = {
                row.status
                for row in await connection.execute(
                    text("select distinct status from library.library_reading")
                )
            }
    finally:
        current_user.reset(token)

    assert (today() - oldest).days > 500
    assert statuses == {"want", "reading", "read", "abandoned"}
