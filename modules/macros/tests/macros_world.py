from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

MODULES = Path(__file__).resolve().parents[2]
OTHERS = ("recipes", "hub")

USDA = {
    "171890": ("Beverages, coffee, brewed", {1008: 1, 1003: 0.1, 1004: 0, 1005: 0, 1057: 40}),
    "171265": (
        "Milk, reduced fat, 2%",
        {1008: 50, 1003: 3.3, 1004: 2, 1005: 4.8, 1087: 120, 1114: 1.2, 1178: 0.5},
    ),
    "172420": (
        "Lentils, raw",
        {1008: 352, 1003: 24.6, 1004: 1.1, 1005: 63.4, 1079: 10.7, 1089: 6.5, 1190: 479},
    ),
    "174841": (
        "Alcoholic beverage, beer, regular",
        {1008: 43, 1003: 0.5, 1004: 0, 1005: 3.6, 1018: 3.9},
    ),
    "173944": ("Bread, white", {1008: 266, 1003: 7.6, 1004: 3.3, 1005: 50.6, 1093: 490}),
}
OFF = {
    "8400000000017": {
        "code": "8400000000017",
        "product_name": "Branded biscuits",
        "nutriments": {
            "energy-kcal_100g": 480,
            "proteins_100g": 6,
            "fat_100g": 20,
            "carbohydrates_100g": 68,
            "sodium_100g": 0.9,
        },
        "product_quantity": 200,
        "product_quantity_unit": "g",
        "serving_quantity": 30,
    }
}


def _usda_food(ref: str, nested: bool) -> dict:
    name, values = USDA[ref]
    nutrients = [
        {"nutrient": {"id": key}, "amount": value}
        if nested
        else {"nutrientId": key, "value": value}
        for key, value in values.items()
    ]
    return {"fdcId": int(ref), "description": name, "foodNutrients": nutrients}


def sources(request: httpx.Request) -> httpx.Response:
    if "nal.usda.gov" in request.url.host:
        if request.method == "POST":
            wanted = [str(one) for one in json.loads(request.content)["fdcIds"]]
            return httpx.Response(
                200, json=[_usda_food(ref, True) for ref in wanted if ref in USDA]
            )
        query = request.url.params["query"].lower()
        found = [
            _usda_food(ref, False)
            for ref, (name, _) in USDA.items()
            if any(word in name.lower() for word in query.split())
        ]
        return httpx.Response(200, json={"foods": found})
    if "/api/v2/product/" in request.url.path:
        code = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        if code in OFF:
            return httpx.Response(200, json={"product": OFF[code]})
        return httpx.Response(404)
    query = request.url.params.get("q", "").lower()
    hits = [one for one in OFF.values() if query in one["product_name"].lower()]
    return httpx.Response(200, json={"hits": hits})


class Router(httpx.AsyncBaseTransport):
    def __init__(self, apps: dict) -> None:
        self.apps = {name: ASGITransport(app=one) for name, one in apps.items()}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.apps[request.url.host].handle_async_request(request)


class Down(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)


class World:
    def __init__(self, recipes: AsyncClient, hub: AsyncClient, monkeypatch) -> None:
        self.recipes = recipes
        self.hub = hub
        self.monkeypatch = monkeypatch

    def recipes_down(self) -> None:
        from kernel import capabilities as kernel_capabilities

        self.monkeypatch.setattr(kernel_capabilities, "module_transport", lambda: Down())

    async def manual_food(self, name: str, macros: dict, **measures) -> str:
        response = await self.recipes.post(
            "/foods/manual",
            json={"name": name, "category_id": "other", "macros": macros, **measures},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def imported(self, query: str, alias: str | None = None, **measures) -> dict:
        found = (await self.recipes.get("/foods/search", params={"q": query})).json()
        candidate = found["candidates"][0]
        response = await self.recipes.post(
            "/foods",
            json={
                **{k: candidate[k] for k in ("source", "source_ref", "name", "macros")},
                "nutrients": candidate["nutrients"],
                "category_id": "other",
                "alias": alias,
                **measures,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()


async def _fresh(connection, module: str) -> None:
    await connection.execute(text(f'drop schema if exists "{module}" cascade'))
    await connection.execute(
        text("delete from kernel.module_migrations where module = :m"), {"m": module}
    )


@pytest.fixture
async def world(schema, database_url, monkeypatch):
    from arga_testing import fresh_modules
    from hub import capabilities as hub_capabilities
    from hub import credentials as hub_credentials
    from hub import db as hub_db
    from hub.main import app as hub_app
    from hub.providers import food as hub_food
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from macros.main import app
    from recipes import db as recipes_db
    from recipes.main import app as recipes_app

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    monkeypatch.setenv("HUB_CREDENTIALS_KEY", os.urandom(32).hex())
    hub_credentials.masters.cache_clear()
    async with schema.begin() as connection:
        await fresh_modules(connection, *OTHERS, "macros", fresh=OTHERS)
    monkeypatch.setattr(
        kernel_capabilities,
        "module_transport",
        lambda: Router({"recipes": recipes_app, "macros": app}),
    )
    monkeypatch.setattr(kernel_capabilities, "hub_transport", lambda: ASGITransport(app=hub_app))
    monkeypatch.setattr(hub_capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    monkeypatch.setattr(hub_capabilities, "source_transport", lambda: httpx.MockTransport(sources))
    monkeypatch.setenv("FOOD_SOURCE_BACKOFF_SECONDS", "0")
    hub_food.forget()
    for cached in (hub_db.engine, recipes_db.engine):
        cached.cache_clear()
    to_kernel = AsyncClient(transport=ASGITransport(app=kernel_app))
    recipes_app.state.client = to_kernel
    app.state.client = to_kernel
    async with (
        AsyncClient(transport=ASGITransport(app=hub_app), base_url="http://hub") as hub,
        AsyncClient(transport=ASGITransport(app=recipes_app), base_url="http://recipes") as recipes,
    ):
        response = await hub.post(
            "/connections", json={"provider": "usda", "secrets": {"api_key": "test-only"}}
        )
        assert response.status_code == 201, response.text
        yield World(recipes, hub, monkeypatch)
    await to_kernel.aclose()
    app.state.client = None
    for cached in (hub_db.engine, kernel_db.engine, recipes_db.engine):
        await cached().dispose()
        cached.cache_clear()
    hub_credentials.masters.cache_clear()
    async with schema.begin() as connection:
        for module in OTHERS:
            await connection.execute(
                text("delete from kernel.modules where id = :id"), {"id": module}
            )
