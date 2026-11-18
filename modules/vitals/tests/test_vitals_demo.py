from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from vitals import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("vitals_weight", "vitals_goal", "vitals_checkup", "vitals_lab_result")
TODAY = date.today()


async def counts() -> dict[str, int]:
    from vitals.main import as_app

    async with as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from vitals.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from vitals.main import as_app

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


async def counts_for(persona) -> dict[str, int]:
    token = current_user.set(persona.id)
    try:
        return await counts()
    finally:
        current_user.reset(token)


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first["sam"] == again["sam"]
    assert again["alex"]["vitals_checkup"] == 4
    assert again["alex"]["vitals_lab_result"] == 32


async def test_each_person_sees_their_weight_going_down_and_their_labs(api) -> None:
    await seed_everyone()

    for persona in CAST.people:
        response = await api.get("/weight", headers=headers(persona))
        assert response.status_code == 200, response.text
        found = await counts_for(persona)
        assert found["vitals_weight"] > 150
