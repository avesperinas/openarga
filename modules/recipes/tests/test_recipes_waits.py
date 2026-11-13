from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import text
from test_recipes_replace import manual, recipe_with

from recipes import hub
from recipes.main import app

OPEN = text("""
    select count(*) from pg_stat_activity
    where datname = current_database() and state = 'idle in transaction' and pid <> pg_backend_pid()
""")


@pytest.fixture
def waits(schema, monkeypatch) -> list[int]:
    seen: list[int] = []

    async def count() -> None:
        async with schema.connect() as connection:
            seen.append(await connection.scalar(OPEN))

    async def search(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
        await count()
        return {"candidates": [], "failed": []}

    async def ask(client: httpx.AsyncClient, capability: str, body: dict) -> httpx.Response:
        await count()
        if capability == "shopping.add":
            return httpx.Response(200, json={"added": [], "pending": 0})
        return httpx.Response(200, json={"items": 0, "entries": 0, "days": []})

    monkeypatch.setattr(hub, "search", search)
    monkeypatch.setattr(hub, "ask", ask)
    app.state.client = httpx.AsyncClient()
    yield seen
    app.state.client = None


async def test_searching_outside_waits_with_no_transaction_open(api, waits) -> None:
    assert (await api.get("/foods/search", params={"q": "yogur"})).status_code == 200
    assert waits == [0]


async def test_the_shopping_list_and_macros_are_asked_with_no_transaction_open(api, waits) -> None:
    milk = await manual(api, "Whole milk")
    oat = await manual(api, "Oat drink")
    recipe = await recipe_with(api, milk["food_id"])

    listed = await api.post(f"/recipes/{recipe}/shopping", json={"positions": [1]})
    replaced = await api.post(f"/foods/{milk['food_id']}/replace", json={"new_id": oat["food_id"]})

    assert listed.status_code == 200, listed.text
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["macros"]["done"] is True
    assert waits == [0, 0]


async def test_a_food_that_fails_to_refill_does_not_stop_publishing(schema, monkeypatch) -> None:
    from arga_contracts.records import Never
    from arga_tenancy import current_user
    from recipes import pantry, publisher

    async def broken(connection, client) -> int:
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(publisher, "RECORDS", Never())
    monkeypatch.setattr(publisher, "HANDED", {"done": True})
    monkeypatch.setattr(pantry, "refill", broken)

    async with httpx.AsyncClient() as client:
        await publisher.refresh(client, current_user.get(), True)
