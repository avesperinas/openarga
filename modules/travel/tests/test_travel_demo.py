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

    assert first == again
    assert first["alex"][0] == 10 and first["sam"][0] == 12


async def test_alex_has_a_past_a_present_and_a_plan_ahead(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[0].id), "x-arga-spaces": str(CAST.space_id)}

    atlas = (await api.get("/atlas", headers=headers)).json()

    phases = {one["title"]: one["phase"] for one in atlas["trips"]}
    assert phases["Flanders in September"] == "done"
    assert phases["Copenhagen long weekend"] == "ongoing"
    assert phases["A long weekend in Lisbon"] == "plan"
    countries = {code for one in atlas["trips"] for code in one["countries"]}
    assert {"ES", "IT", "DE", "BE", "DK", "NL", "GB", "PT"} <= countries


async def test_sam_sees_the_trips_alex_shared_and_their_own(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[1].id), "x-arga-spaces": str(CAST.space_id)}

    atlas = (await api.get("/atlas", headers=headers)).json()

    titles = {one["title"] for one in atlas["trips"]}
    assert {"Flanders in September", "Tenerife en julio", "Fin de semana en Praga"} <= titles


async def test_each_person_reads_the_trips_in_their_own_language(schema) -> None:
    from travel.main import as_app

    await seed_everyone()
    found = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        try:
            async with as_app() as connection:
                found[persona.key] = set(
                    await connection.scalars(text("select title from travel.travel_trip"))
                )
        finally:
            current_user.reset(token)

    assert {"Flanders in September"} <= found["alex"]
    assert {"Fin de semana en Praga"} <= found["sam"]
    assert not {"Prague weekend"} & found["sam"]
