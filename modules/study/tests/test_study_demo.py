from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from study import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TODAY = date.today()
COUNTS = """
    select (select count(*) from study.study_course) as courses,
           (select count(*) from study.study_subject) as subjects,
           (select count(*) from study.study_assessment) as assessments,
           (select count(*) from study.study_schedule) as schedules
"""


async def seed_everyone() -> dict[str, tuple[int, ...]]:
    from study.main import as_app

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
    assert first["alex"][0] == 3 and first["sam"][0] == 3


async def test_alex_has_a_grade_to_chase_and_sessions_this_week(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[0].id)}

    home = (await api.get("/home", headers=headers)).json()

    assert "Master in Data Science" in [one["name"] for one in home["courses"]]
    assert any(day["sessions"] for day in home["days"])
    assert [one["title"] for one in home["upcoming"]][:1] == ["Lab 2"]


async def test_each_person_reads_the_courses_in_their_own_language(schema) -> None:
    from study.main import as_app

    await seed_everyone()
    found = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        try:
            async with as_app() as connection:
                found[persona.key] = set(
                    await connection.scalars(text("select name from study.study_course"))
                )
        finally:
            current_user.reset(token)

    assert {"Master in Data Science"} <= found["alex"]
    assert {"Italiano A2"} <= found["sam"]
    assert not {"Italian A2"} & found["sam"]
