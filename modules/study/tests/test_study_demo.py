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

    assert first == again == {"alex": (1, 2, 4, 1), "sam": (1, 0, 0, 1)}


async def test_alex_has_a_grade_to_chase_and_sessions_this_week(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[0].id)}

    home = (await api.get("/home", headers=headers)).json()

    assert [one["name"] for one in home["courses"]] == ["Master in Data Science"]
    assert any(day["sessions"] for day in home["days"])
    assert [one["title"] for one in home["upcoming"]][:1] == ["Lab 2"]
