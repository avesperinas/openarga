from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from notebook import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TODAY = date.today()


async def seed_everyone() -> dict[str, int]:
    from notebook.main import as_app

    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            async with as_app() as connection:
                await demo.seed(connection, persona, TODAY)
                seen[persona.key] = await connection.scalar(
                    text("select count(*) from notebook.notebook_note where deleted_at is null")
                )
        finally:
            current_spaces.reset(spaces)
            current_user.reset(token)
    return seen


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first == again == {"alex": 12, "sam": 10}


async def test_alex_has_linked_notes_a_journal_and_something_to_review(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[0].id)}

    tree = (await api.get("/tree", headers=headers)).json()
    review = (await api.get("/review", headers=headers)).json()
    graph = (await api.get("/graph", headers=headers)).json()

    assert {"Journal", "Study/German", "Projects/Home"} <= set(tree["folders"])
    assert review["chosen"] and [n["title"] for n in review["notes"]] == ["Dative prepositions"]
    assert len(graph["edges"]) >= 3
