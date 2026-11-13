from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from recipes import pantry

LENTILS = {
    "foods": [
        {
            "fdcId": 172420,
            "description": "Lentils, raw",
            "foodCategory": "Legumes and Legume Products",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 352},
                {"nutrientId": 1003, "value": 24.6},
                {"nutrientId": 1004, "value": 1.1},
                {"nutrientId": 1005, "value": 63.4},
                {"nutrientId": 1079, "value": 10.7},
                {"nutrientId": 1089, "value": 6.5},
                {"nutrientId": 1190, "value": 479},
                {"nutrientId": 1093, "value": 6},
            ],
        }
    ]
}
LENTILS_DETAIL = [
    {
        "fdcId": 172420,
        "description": "Lentils, raw",
        "foodNutrients": [
            {"nutrient": {"id": 1008}, "amount": 352},
            {"nutrient": {"id": 1003}, "amount": 24.6},
            {"nutrient": {"id": 1004}, "amount": 1.1},
            {"nutrient": {"id": 1005}, "amount": 63.4},
            {"nutrient": {"id": 1089}, "amount": 6.5},
        ],
    }
]


def sources(request: httpx.Request) -> httpx.Response:
    if "nal.usda.gov" in request.url.host:
        if request.method == "POST":
            return httpx.Response(200, json=LENTILS_DETAIL)
        return httpx.Response(200, json=LENTILS)
    return httpx.Response(200, json={"hits": []})


@pytest.fixture
async def with_sources(hub):
    await hub.with_usda()
    hub.answer(sources)
    return hub


async def import_lentils(api) -> dict:
    [candidate] = (await api.get("/foods/search", params={"q": "lentils"})).json()["candidates"]
    response = await api.post(
        "/foods",
        json={
            **{k: candidate[k] for k in ("source", "source_ref", "name", "macros", "nutrients")},
            "category_id": "legume",
            "alias": "lentejas",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_lentils_from_usda_bring_iron_and_folate(api, with_sources) -> None:
    lentils = await import_lentils(api)

    assert lentils["nutrients"]["iron"] == 6.5
    assert lentils["nutrients"]["folate"] == 479
    assert "vitamin_d" not in lentils["nutrients"]
    [again] = (await api.get("/foods", params={"query": "lentejas"})).json()
    assert again["nutrients"]["iron"] == 6.5


async def test_the_recipe_shows_its_micros_per_serving_with_their_coverage(
    api, with_sources
) -> None:
    lentils = await import_lentils(api)
    salt = (
        await api.post(
            "/foods/manual",
            json={
                "name": "Home chorizo",
                "category_id": "protein",
                "macros": {"kcal": 400, "protein": 20, "fat": 35, "carbs": 0},
            },
        )
    ).json()
    recipe = (
        await api.post(
            "/recipes",
            json={
                "name": "Lentils",
                "servings": 4,
                "ingredients": [
                    {"food_id": lentils["id"], "quantity": 400, "unit": "g"},
                    {"food_id": salt["id"], "quantity": 100, "unit": "g"},
                ],
            },
        )
    ).json()

    nutrition = recipe["nutrition"]
    assert nutrition["nutrients"]["iron"] == pytest.approx(6.5)
    assert nutrition["nutrients"]["folate"] == pytest.approx(479)
    assert nutrition["coverage"]["iron"] == pytest.approx(1408 / 1808, abs=0.001)
    assert nutrition["coverage"]["kcal"] == 1.0


async def test_what_was_imported_before_micros_gets_them_from_its_source(
    api, schema, with_sources
) -> None:
    lentils = await import_lentils(api)
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "update recipes.recipes_food set nutrients = null, "
                "nutrients_checked_at = null where id = cast(:id as uuid)"
            ),
            {"id": lentils["id"]},
        )

    from recipes.main import app

    async with pantry_connection(schema) as connection:
        assert await pantry.refill(connection, app.state.client) == 1
        assert await pantry.refill(connection, app.state.client) == 0

    [again] = (await api.get("/foods", params={"query": "lentejas"})).json()
    assert again["nutrients"]["iron"] == 6.5


def pantry_connection(schema):
    from contextlib import asynccontextmanager

    from recipes.db import engine

    @asynccontextmanager
    async def connect():
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_recipes"'))
            yield connection

    return connect()


PROBE = "probe_macros"


@pytest.fixture
async def kernel(with_sources, schema, monkeypatch):
    from kernel import capabilities as kernel_capabilities
    from kernel.main import app as kernel_app
    from recipes.main import app as recipes_app

    monkeypatch.setattr(
        kernel_capabilities, "module_transport", lambda: ASGITransport(app=recipes_app)
    )

    async def declare(uses: list[str]) -> None:
        async with schema.begin() as connection:
            await connection.execute(
                text(
                    "insert into kernel.modules (id, version, enabled, manifest) "
                    "values (:id, '0.1.0', true, cast(:manifest as jsonb)) "
                    "on conflict (id) do update set manifest = excluded.manifest"
                ),
                {"id": PROBE, "manifest": json.dumps({"uses": uses})},
            )

    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://k") as client:
        client.declare = declare  # type: ignore[attr-defined]
        yield client
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :id"), {"id": PROBE})


def ask(kernel, service: str, body: dict):
    return kernel.post(
        f"/internal/capabilities/{service}", json=body, headers={"x-arga-module": PROBE}
    )


async def test_an_app_that_uses_pantry_search_finds_the_lentils_through_the_kernel(
    api, kernel
) -> None:
    await import_lentils(api)
    await kernel.declare(["pantry.search", "pantry.nutrients"])

    response = await ask(kernel, "pantry.search", {"query": "lentejas", "outside": False})

    assert response.status_code == 200, response.text
    [found] = response.json()["foods"]
    assert (found["label"], found["nutrients"]["iron"]) == ("lentejas", 6.5)
    again = await ask(kernel, "pantry.nutrients", {"ids": [found["id"], "not-an-id"]})
    assert [one["id"] for one in again.json()["foods"]] == [found["id"]]


async def test_without_enough_in_the_pantry_it_looks_outside_too(api, kernel) -> None:
    await kernel.declare(["pantry.search", "pantry.import"])

    found = (await ask(kernel, "pantry.search", {"query": "lentils"})).json()

    assert found["foods"] == []
    [candidate] = found["candidates"]
    assert candidate["nutrients"]["folate"] == 479
    imported = await ask(
        kernel,
        "pantry.import",
        {"source": candidate["source"], "source_ref": candidate["source_ref"], "alias": "lentejas"},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["nutrients"]["iron"] == 6.5
    assert "folate" not in imported.json()["nutrients"]
    [again] = (await api.get("/foods", params={"query": "lentejas"})).json()
    assert again["id"] == imported.json()["id"]


async def test_a_recipe_is_found_and_gives_its_serving_and_version(api, kernel) -> None:
    lentils = await import_lentils(api)
    recipe = (
        await api.post(
            "/recipes",
            json={
                "name": "Stewed lentils",
                "servings": 2,
                "ingredients": [{"food_id": lentils["id"], "quantity": 200, "unit": "g"}],
            },
        )
    ).json()
    await kernel.declare(["recipes.search", "recipes.nutrients"])

    [found] = (await ask(kernel, "recipes.search", {"query": "stewed"})).json()["recipes"]
    serving = (await ask(kernel, "recipes.nutrients", {"id": found["id"]})).json()

    assert serving["version_id"] == recipe["version_id"]
    assert serving["per_serving"]["iron"] == pytest.approx(6.5)
    assert serving["grams_per_serving"] == 100
    assert serving["missing"] == []


async def test_an_app_that_does_not_declare_it_is_refused(api, kernel) -> None:
    await kernel.declare(["pantry.nutrients"])

    response = await ask(kernel, "pantry.search", {"query": "lentejas"})

    assert response.status_code == 403
    assert "pantry.search" in response.json()["detail"]


async def test_nobody_reaches_the_pantry_skipping_the_kernel(api) -> None:
    response = await api.post("/capabilities/pantry.search", json={"query": "lentejas"})
    assert response.status_code in (401, 503)
