from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from test_recipes_recipes import leek_soup, pantry  # noqa: F401 - the fixture is used by name

from recipes.main import MODULE_ID, app
from recipes.shopping import quantity_label


@pytest.fixture
async def shopping(schema, database_url, monkeypatch):
    import secrets

    from arga_testing import fresh_modules
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from shopping import db as shopping_db
    from shopping.main import app as shopping_app

    kernel_db.engine.cache_clear()
    shopping_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    async with schema.begin() as connection:
        await fresh_modules(connection, MODULE_ID, "shopping", fresh=["shopping"])
    monkeypatch.setattr(
        kernel_capabilities, "module_transport", lambda: ASGITransport(app=shopping_app)
    )
    app.state.client = AsyncClient(transport=ASGITransport(app=kernel_app))
    async with AsyncClient(
        transport=ASGITransport(app=shopping_app), base_url="http://shopping"
    ) as client:
        yield client
    await app.state.client.aclose()
    for cached in (kernel_db.engine, shopping_db.engine):
        await cached().dispose()
        cached.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'shopping'"))


def test_quantities_read_as_in_the_recipe() -> None:
    assert quantity_label(400, "g") == "400 g"
    assert quantity_label(1.5, "unit") == "1,5 ud"
    assert quantity_label(2.333, "tbsp") == "2,33 cda"


async def positions(api, recipe_id: str, servings: int | None = None) -> dict[str, int]:
    query = f"?servings={servings}" if servings else ""
    recipe = (await api.get(f"/recipes/{recipe_id}{query}")).json()
    return {one["name"]: one["position"] for g in recipe["groups"] for one in g["ingredients"]}


async def test_the_chosen_ingredients_reach_the_list_scaled(api, pantry, shopping) -> None:  # noqa: F811
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()
    where = await positions(api, recipe["id"])

    response = await api.post(
        f"/recipes/{recipe['id']}/shopping",
        json={"servings": 2, "positions": [where["Leek"], where["Potato"]]},
    )

    assert response.status_code == 200, response.text
    assert [one["name"] for one in response.json()["added"]] == ["Leek", "Potato"]
    listed = (await shopping.get("/list")).json()
    items = {i["name"]: i["quantity"] for s in listed["groups"] for i in s["items"]}
    assert items == {"Leek": "200 g", "Potato": "300 g"}


async def test_what_was_already_on_the_list_stays_as_it_was(api, pantry, shopping) -> None:  # noqa: F811
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()
    where = await positions(api, recipe["id"])
    body = {"positions": [where["Leek"]]}

    await api.post(f"/recipes/{recipe['id']}/shopping", json=body)
    again = await api.post(f"/recipes/{recipe['id']}/shopping", json=body)

    assert again.json()["added"] == [{"name": "Leek", "already_on_list": True}]
    assert again.json()["pending"] == 1


async def test_without_declaring_it_the_kernel_says_no(api, pantry, shopping, schema) -> None:  # noqa: F811
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()
    where = await positions(api, recipe["id"])
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "update kernel.modules set manifest = jsonb_set(manifest, '{uses}', "
                "cast(:uses as jsonb)) where id = :m"
            ),
            {"uses": json.dumps(["food.search"]), "m": MODULE_ID},
        )

    response = await api.post(
        f"/recipes/{recipe['id']}/shopping", json={"positions": [where["Leek"]]}
    )

    assert response.status_code == 503
    assert "uses" in response.json()["detail"]
    assert (await shopping.get("/list")).json()["pending"] == 0


async def test_shopping_refuses_whoever_does_not_come_from_the_kernel(shopping) -> None:
    response = await shopping.post("/capabilities/shopping.add", json={"items": [{"name": "Leek"}]})

    assert response.status_code == 401


async def test_when_the_list_is_down_the_recipe_says_so(api, pantry, shopping, monkeypatch) -> None:  # noqa: F811
    import httpx

    from kernel import capabilities as kernel_capabilities

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("not there")

    monkeypatch.setattr(kernel_capabilities, "module_transport", lambda: httpx.MockTransport(down))
    recipe = (await api.post("/recipes", json=leek_soup(pantry))).json()
    where = await positions(api, recipe["id"])

    response = await api.post(
        f"/recipes/{recipe['id']}/shopping", json={"positions": [where["Leek"]]}
    )

    assert response.status_code == 503
    assert "shopping" in response.json()["detail"]
