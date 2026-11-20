from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from insights import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TODAY = datetime.now(UTC).date()
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

    assert first == again == {"alex": (2, 2, 12), "sam": (2, 2, 10)}


async def test_alex_has_advice_a_week_and_today_s_pill(api) -> None:
    await seed_everyone()
    headers = {"x-arga-user": str(CAST.people[0].id), "x-arga-timezone": "UTC"}

    inbox = (await api.get("/insights", headers=headers)).json()
    badge = (await api.get("/badge", headers=headers)).json()

    assert {one["kind"] for one in inbox} == {"alert", "weekly"}
    assert badge["count"] >= 3


async def test_each_person_reads_the_pills_in_their_own_language(schema) -> None:
    from insights.main import as_role

    await seed_everyone()
    found = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        try:
            async with as_role("mod_insights") as connection:
                found[persona.key] = set(
                    await connection.scalars(text("select headline from insights.insights_pill"))
                )
        finally:
            current_user.reset(token)

    assert {"The column that broke Sparta"} <= found["alex"]
    assert {"Un animal que saborea lo que toca"} <= found["sam"]
    assert not {"An animal that tastes what it touches"} & found["sam"]
