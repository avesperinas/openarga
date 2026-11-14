from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from insights import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TODAY = date.today()
COUNTS = """
    select (select count(*) from insights.insights_insight) as insights,
           (select count(*) from insights.insights_pill) as pills,
           (select count(*) from insights.insights_trait) as traits
"""


async def seed_everyone() -> dict[str, tuple[int, int, int]]:
    from insights.main import as_role

    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            async with as_role("mod_insights") as connection:
                await demo.seed(connection, persona, TODAY)
                seen[persona.key] = tuple((await connection.execute(text(COUNTS))).one())
        finally:
            current_spaces.reset(spaces)
            current_user.reset(token)
    return seen


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first == again == {"alex": (2, 2, 3), "sam": (2, 2, 3)}


async def test_alex_has_advice_a_week_and_today_s_pill(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[0].id), "x-arga-timezone": "UTC"}

    inbox = (await api.get("/insights", headers=headers)).json()
    badge = (await api.get("/badge", headers=headers)).json()

    assert {one["kind"] for one in inbox} == {"alert", "weekly"}
    assert badge["count"] >= 3
