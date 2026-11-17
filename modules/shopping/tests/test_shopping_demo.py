from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from arga_module import demo as cast_of
from arga_tenancy import current_spaces, current_user
from shopping import demo

CAST = cast_of.load(Path(__file__).resolve().parents[3] / "demo" / "personas.yaml")
TABLES = ("shopping_product", "shopping_trip", "shopping_item", "shopping_setting")
TODAY = date.today()


async def counts() -> dict[str, int]:
    from shopping.main import service

    async with service.as_app() as connection:
        return {
            table: await connection.scalar(text(f"select count(*) from shopping.{table}"))
            for table in TABLES
        }


async def seed_everyone() -> dict[str, dict[str, int]]:
    from shopping.main import service

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

    assert first["sam"] == again["alex"] == again["sam"]
    assert first["sam"]["shopping_trip"] == 78
    assert first["sam"]["shopping_product"] == len(demo.PRODUCTS)


async def test_alex_and_sam_share_one_list_and_its_trips(api) -> None:
    await seed_everyone()

    for persona in CAST.people:
        listing = (await api.get("/list", headers=headers(persona))).json()
        names = {item["name"] for group in listing["groups"] for item in group["items"]}
        assert {"Milk", "Bread", "Apples"} <= names
        trips = (await api.get("/trips", params={"limit": 100}, headers=headers(persona))).json()
        assert len(trips) == 78
