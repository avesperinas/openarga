from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from planner import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("planner_calendar", "planner_event")
TODAY = date.today()


async def counts() -> dict[str, int]:
    from planner.main import as_app

    async with as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from planner.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from planner.main import as_app

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


async def test_the_seed_runs_twice_without_duplicates(schema) -> None:
    first = await seed_everyone()
    again = await seed_everyone()

    assert first == again
    assert first["alex"] == {"planner_calendar": 4, "planner_event": 11}
    assert first["sam"] == {"planner_calendar": 4, "planner_event": 11}


async def test_alex_and_sam_share_home_and_their_work_rests_on_local_holidays(api) -> None:
    await seed_everyone()
    window = {
        "from": f"{TODAY}T00:00:00+00:00",
        "to": f"{TODAY + timedelta(days=28)}T00:00:00+00:00",
    }

    for persona in CAST.people:
        headers = {"x-arga-user": str(persona.id), "x-arga-spaces": str(CAST.space_id)}
        layers = {one["name"]: one for one in (await api.get("/calendars", headers=headers)).json()}
        found = (await api.get("/occurrences", params=window, headers=headers)).json()
        titles = {one["title"] for one in found}

        assert {"Personal", "Work", "Local holidays", "Home"} <= set(layers)
        assert layers["Work"]["days_off_from"] == [layers["Local holidays"]["id"]]
        assert {"Dentist", "Town festival", "Plumber visit", "Weekly shop"} <= titles
        festival = TODAY + timedelta(days=20)
        work_days = {one["start"][:10] for one in found if one["title"] == "Workday"}
        assert len(work_days) >= 15
        assert festival.isoformat() not in work_days
