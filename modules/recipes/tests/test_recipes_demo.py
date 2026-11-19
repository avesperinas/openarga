from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from recipes import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("recipes_recipe", "recipes_recipe_version", "recipes_step")
TODAY = date.today()


async def counts() -> dict[str, int]:
    from recipes.main import service

    async with service.as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from recipes.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from recipes.main import service

    seen = {}
    for persona in CAST.people:
        token = current_user.set(persona.id)
        spaces = current_spaces.set((CAST.space_id,))
        try:
            async with service.as_app() as connection:
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
    assert again["alex"]["recipes_recipe"] >= 18
    assert again["sam"]["recipes_recipe"] >= 18


async def test_alex_and_sam_see_their_recipes_and_the_shared_ones(api) -> None:
    await seed_everyone()
    alex, sam = CAST.people

    mine = {one["name"] for one in (await api.get("/recipes", headers=headers(alex))).json()}
    theirs = {one["name"] for one in (await api.get("/recipes", headers=headers(sam))).json()}
    assert {"Lentil stew", "Baked salmon with vegetables", "Potato omelette"} <= mine
    assert {"Lentil stew", "Potato omelette", "Hummus"} <= theirs
    assert "Baked salmon with vegetables" not in theirs
