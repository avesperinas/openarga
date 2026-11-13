from __future__ import annotations

from datetime import time

from sqlalchemy import text

from macros import notices
from macros.common import today


async def build(schema) -> list[dict]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_macros"'))
        return await notices.build(connection)


async def test_without_a_protein_target_there_is_nothing_to_say(api, schema) -> None:
    assert await build(schema) == []


async def test_what_is_missing_is_said_at_the_chosen_hour_until_it_is_reached(
    api, schema, world
) -> None:
    await api.put("/target", json={"kcal": 2200, "protein": 140})
    saved = (await api.put("/settings", json={"protein_at": "21:30"})).json()

    [missing] = await build(schema)

    assert saved["protein_at"].startswith("21:30")
    assert missing["kind"] == "protein"
    assert missing["key"] == f"protein:{today().isoformat()}"
    assert missing["title"] == "140 g of protein to go"
    assert missing["at"].startswith(f"{today().isoformat()}T21:30")

    entry = {
        "items": [
            {
                "kind": "quick",
                "name": "Batido",
                "quantity": 600,
                "unit": "kcal",
                "quick": {"protein": 150},
            }
        ]
    }
    created = await api.post("/entries", json=entry)
    assert created.status_code == 201, created.text
    assert await build(schema) == []


async def test_without_a_saved_hour_it_is_eight_in_the_evening(api, schema) -> None:
    assert (await api.get("/settings")).json()["protein_at"].startswith("20:00")
    assert time(20, 0) == notices.DEFAULT_AT
