from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from travel import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TODAY = date.today()
COUNTS = """
    select (select count(*) from travel.travel_trip) as trips,
           (select count(*) from travel.travel_stay) as stays,
           (select count(*) from travel.travel_expense) as expenses,
           (select count(*) from travel.travel_idea) as ideas
"""


async def seed_everyone() -> dict[str, tuple[int, ...]]:
    from travel.main import as_app

    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            async with as_app() as connection:
                await demo.seed(connection, persona, TODAY)
                seen[persona.key] = tuple((await connection.execute(text(COUNTS))).one())
        finally:
            current_spaces.reset(spaces)
            current_user.reset(token)
    return seen


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first == again == {"alex": (2, 3, 3, 0), "sam": (1, 1, 1, 1)}


async def test_alex_has_a_trip_made_and_a_plan_ahead(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[0].id)}

    atlas = (await api.get("/atlas", headers=headers)).json()

    phases = {one["title"]: one["phase"] for one in atlas["trips"]}
    assert phases == {"Flanders in spring": "done", "A long weekend in Lisbon": "plan"}
    flanders = next(one for one in atlas["trips"] if one["phase"] == "done")
    assert flanders["countries"] == ["BE"] and flanders["nights"] == 3
