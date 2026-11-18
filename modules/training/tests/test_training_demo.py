from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from training import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("training_plan", "training_rotation", "training_session", "training_set_log")
TODAY = date.today()


async def counts() -> dict[str, int]:
    from training.main import as_app

    async with as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from training.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from training.main import as_app

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
    assert again["alex"]["training_plan"] == 1
    assert again["alex"]["training_session"] > 200


async def test_each_person_sees_their_sessions_and_their_catalogue(schema) -> None:
    from httpx import ASGITransport, AsyncClient

    from training.main import app

    await seed_everyone()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as api:
        for persona in CAST.people:
            sessions = await api.get("/sessions", headers=headers(persona))
            assert sessions.status_code == 200, sessions.text
            assert sessions.json()
            catalogue = (await api.get("/catalogue", headers=headers(persona))).json()
            names = {one["name"] for one in catalogue["exercises"]}
            assert ("Bench press" if persona.locale == "en" else "Press de banca") in names
