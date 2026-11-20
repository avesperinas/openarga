from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from goals import demo
from goals.common import today

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("goals_category", "goals_task", "goals_goal", "goals_goal_check", "goals_person")
TODAY = today()


async def counts() -> dict[str, int]:
    from goals.main import as_app

    async with as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from goals.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from goals.main import as_app

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

    assert first == again
    assert first["alex"]["goals_goal"] == 7
    assert first["alex"]["goals_task"] > 200


async def test_alex_and_sam_see_their_day_their_goals_and_the_shared_category(api) -> None:
    await seed_everyone()
    alex, sam = CAST.people

    for persona in (alex, sam):
        names = [
            one["name"] for one in (await api.get("/categories", headers=headers(persona))).json()
        ]
        assert "Household" in names
        pending = (await api.get("/tasks", headers=headers(persona))).json()
        statuses = {one["status"] for one in pending}
        assert {"overdue", "today", "upcoming", "someday"} <= statuses
        active = (await api.get("/goals", headers=headers(persona))).json()
        title = "Read 20 minutes" if persona.locale == "en" else "Leer 20 minutos"
        reading = next(one for one in active if one["title"] == title)
        assert reading["streak"] or reading["constancy"]
        closed = await api.get("/goals", params={"state": "closed"}, headers=headers(persona))
        assert {one["status"] for one in closed.json()} == {"achieved", "missed"}

    spanish = [one["name"] for one in (await api.get("/categories", headers=headers(sam))).json()]
    assert "Trabajo" in spanish


async def test_each_person_reads_the_tasks_in_their_own_language(schema) -> None:
    from goals.main import as_app

    await seed_everyone()
    found = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        try:
            async with as_app() as connection:
                found[persona.key] = set(
                    await connection.scalars(
                        text("select title from goals.goals_task where space_id is null")
                    )
                )
        finally:
            current_user.reset(token)

    assert {"Send the weekly report"} <= found["alex"]
    assert {"Enviar el informe semanal"} <= found["sam"]
    assert not {"Send the weekly report"} & found["sam"]
