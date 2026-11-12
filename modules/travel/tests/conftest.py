from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import current_user, install
from travel import db
from travel.main import MODULE_ID, app

SCHEMA = db.SCHEMA
MODULES = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)


@pytest.fixture(scope="session")
def database_url() -> str:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    db.engine.cache_clear()
    return TEST_DATABASE_URL


@pytest.fixture
async def schema(database_url: str):
    from arga_testing import fresh_modules

    setup = install(create_async_engine(database_url))
    async with setup.begin() as connection:
        await fresh_modules(connection, MODULE_ID)

    yield setup

    async with setup.begin() as connection:
        await connection.execute(
            text("delete from kernel.modules where id = :id"), {"id": MODULE_ID}
        )
    await setup.dispose()
    await db.engine().dispose()
    db.engine.cache_clear()


@pytest.fixture
async def api(schema):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://travel") as client:
        yield client


PERSON = UUID("00000000-0000-4000-8000-00000000a7e5")
OTHER = UUID("00000000-0000-4000-8000-00000000b0b0")


@pytest.fixture(autouse=True)
def person(request: pytest.FixtureRequest):
    if "database_url" not in request.fixturenames:
        yield None
        return
    token = current_user.set(PERSON)
    yield PERSON
    current_user.reset(token)


class Hub:
    STREETS = MODULES / "outings/ui/public/map/pamplona/region.pmtiles"

    def __init__(self) -> None:
        self.down = False
        self.asked: list[str] = []
        self.places: list[dict] = []
        self.tiles_asked = 0
        self.routes: list[str] = []
        self.near: list[dict] = []
        self.nearby_asked = 0

    def __call__(self, request):
        import httpx

        if self.down:
            raise httpx.ConnectError("sin red", request=request)
        if request.url.host == "build-metadata.protomaps.dev":
            return httpx.Response(200, json=[{"key": "20261001.pmtiles"}])
        if request.url.host == "build.protomaps.com":
            self.tiles_asked += 1
            first, last = request.headers["range"].split("=")[1].split("-")
            return httpx.Response(
                206, content=self.STREETS.read_bytes()[int(first) : int(last) + 1]
            )
        if request.url.host == "api.frankfurter.dev":
            if request.url.params["base"] == "VND":
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(
                200, json={"base": "JPY", "date": "2027-04-02", "rates": {"EUR": 0.00565}}
            )
        if request.url.host == "api.open-meteo.com":
            return httpx.Response(
                200,
                json={
                    "timezone": "Asia/Tokyo",
                    "daily": {
                        "time": ["2027-11-01"],
                        "weather_code": [2],
                        "temperature_2m_max": [17.0],
                        "temperature_2m_min": [9.0],
                        "precipitation_probability_max": [10],
                    },
                },
            )
        if request.url.host == "archive-api.open-meteo.com":
            return httpx.Response(
                200,
                json={
                    "timezone": "Asia/Tokyo",
                    "daily": {
                        "time": ["2024-11-01", "2024-11-02"],
                        "temperature_2m_max": [16.0, 18.0],
                        "temperature_2m_min": [8.0, 10.0],
                        "precipitation_sum": [0.0, 5.0],
                    },
                },
            )
        if request.url.host == "overpass-api.de":
            self.nearby_asked += 1
            return httpx.Response(200, json={"elements": self.near})
        if request.url.host == "routing.openstreetmap.de":
            self.routes.append(str(request.url.path))
            stops = request.url.path.rsplit("/", 1)[1].split(";")
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "routes": [
                        {
                            "distance": 600.0 * (len(stops) - 1),
                            "duration": 450.0 * (len(stops) - 1),
                            "legs": [{"distance": 600.0, "duration": 450.0}] * (len(stops) - 1),
                            "geometry": {
                                "coordinates": [[float(c) for c in s.split(",")] for s in stops]
                            },
                        }
                    ],
                },
            )
        self.asked.append(request.url.params.get("q", ""))
        return httpx.Response(200, json=self.places)


@pytest.fixture
async def hub(schema, database_url, monkeypatch):
    import asyncio
    import secrets

    import httpx

    from arga_testing import fresh_modules
    from hub import capabilities
    from hub import credentials as hub_credentials
    from hub import db as hub_db
    from hub.main import app as hub_app
    from hub.providers import fx, maps, nearby, places, routes, weather
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from travel import hub as travel_hub

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    monkeypatch.setenv("HUB_CREDENTIALS_KEY", os.urandom(32).hex())
    hub_credentials.masters.cache_clear()
    async with schema.begin() as connection:
        await fresh_modules(connection, MODULE_ID, "hub", fresh=["hub"])
    fake = Hub()
    monkeypatch.setattr(places, "PACE", places._Pace())
    monkeypatch.setattr(places, "MIN_INTERVAL", 0.0)
    monkeypatch.setattr(maps, "ARCHIVE", maps._Archive())
    monkeypatch.setattr(routes, "CACHE", {})
    monkeypatch.setattr(weather, "CACHE", {})
    monkeypatch.setattr(fx, "CACHE", {})
    monkeypatch.setattr(nearby, "PACE", nearby._Pace())
    monkeypatch.setattr(nearby, "MIN_INTERVAL", 0.0)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(kernel_capabilities, "hub_transport", lambda: ASGITransport(app=hub_app))
    monkeypatch.setattr(travel_hub, "transport", lambda: ASGITransport(app=kernel_app))
    hub_db.engine.cache_clear()
    yield fake
    for cached in (hub_db.engine, kernel_db.engine):
        await cached().dispose()
        cached.cache_clear()
    hub_credentials.masters.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'hub'"))
