from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from macros import demo
from macros.common import today

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("macros_target", "macros_entry", "macros_item", "macros_day_complete")
TODAY = today()


async def counts() -> dict[str, int]:
    from macros.main import as_app

    async with as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from macros.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from macros.main import as_app

    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            async with as_app() as connection:
                await demo.seed(connection, persona, TODAY)
            seen[persona.key] = await counts()
        finally:
            current_spaces.reset(spaces)
            current_user.reset(token)
    return seen


def headers(persona, locale: str | None = None) -> dict[str, str]:
    found = {"x-arga-user": str(persona.id), "x-arga-spaces": str(CAST.space_id)}
    found["x-arga-locale"] = locale or persona.locale
    found["x-arga-timezone"] = persona.timezone
    return found


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first["sam"] == again["sam"]
    assert again["alex"]["macros_target"] == 1
    assert again["alex"]["macros_entry"] > 800


async def test_each_person_has_today_and_a_week_against_the_target(api) -> None:
    await seed_everyone()

    for persona in CAST.people:
        day = await api.get("/day", headers=headers(persona))
        assert day.status_code == 200, day.text
        week = await api.get("/week", headers=headers(persona))
        assert week.status_code == 200, week.text


async def test_each_person_has_goals_templates_and_training_days(schema) -> None:
    from macros.main import as_app

    await seed_everyone()
    for persona in CAST.people:
        token = current_user.set(persona.id)
        try:
            async with as_app() as connection:
                found = {
                    table: await connection.scalar(text(f"select count(*) from macros.{table}"))
                    for table in ("macros_goal", "macros_template", "macros_day_kind")
                }
        finally:
            current_user.reset(token)
        assert found["macros_goal"] >= 4
        assert found["macros_template"] == 3
        assert found["macros_day_kind"] >= 28
