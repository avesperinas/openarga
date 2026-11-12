from __future__ import annotations

import os
import secrets
import sys
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import USER_HEADER, current_user, install
from outings import common, db, profile
from outings.main import MODULE_ID, app

SCHEMA = db.SCHEMA


def _pin_the_day() -> None:
    real_now, real_today = common.now, common.today
    day = real_today()

    def now() -> datetime:
        moment = real_now()
        return moment + (day - moment.date())

    def today() -> date:
        return day

    for name, module in list(sys.modules.items()):
        if name == "outings" or name.startswith("outings."):
            if getattr(module, "now", None) is real_now:
                module.now = now
            if getattr(module, "today", None) is real_today:
                module.today = today


_pin_the_day()
MODULES = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)


@pytest.fixture(params=profile.ids())
def area(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> profile.Profile:
    monkeypatch.setenv("OPENARGA_AREA", request.param)
    return profile.load(request.param)


@pytest.fixture(scope="session")
def database_url() -> str:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    db.engine.cache_clear()
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def kernel_schema(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()
    kernel_db.engine.cache_clear()


@pytest.fixture
async def schema(database_url: str, kernel_schema: None):
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://outings") as client:
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
    def __init__(self) -> None:
        self.down = False
        self.asked: list[str] = []
        self.places: list[dict] = []
        self.photos: dict[str, str] = {}
        self.photo_asks: list[str] = []
        self.around: list[str] = []

    def __call__(self, request):
        import httpx

        url, params = request.url, request.url.params
        if self.down:
            raise httpx.ConnectError("no network", request=request)
        if url.host == "nominatim.openstreetmap.org":
            self.asked.append(params.get("q", ""))
            return httpx.Response(200, json=self.places)
        if url.host == "www.wikidata.org":
            if "-haswbstatement:P625" in params.get("srsearch", ""):
                return httpx.Response(200, json={"query": {"search": []}})
            if params.get("list") == "search":
                words = params["srsearch"].split(" haswbstatement")[0]
                self.photo_asks.append(words)
                hits = [{"title": f"Q{len(words)}"}] if words in self.photos else []
                self._last = words
                return httpx.Response(200, json={"query": {"search": hits}})
            value = self.photos[self._last]
            claims = [{"mainsnak": {"datavalue": {"value": value}}}]
            return httpx.Response(200, json={"claims": {"P18": claims}})
        if url.host == "www.openstreetmap.org":
            return httpx.Response(200, json={"elements": [{"tags": {}}]})
        if url.host == "commons.wikimedia.org" and params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": []}})
        if url.host == "commons.wikimedia.org" and params.get("list") == "geosearch":
            hits = [{"title": f"File:{one}"} for one in self.around]
            return httpx.Response(200, json={"query": {"geosearch": hits}})
        if url.host == "commons.wikimedia.org":
            info = {
                "thumburl": "https://upload.wikimedia.org/x/1600px-foto.jpg",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/{params['titles']}",
                "extmetadata": {
                    "Artist": {"value": "Synthetic Author"},
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                },
            }
            return httpx.Response(200, json={"query": {"pages": {"1": {"imageinfo": [info]}}}})
        if url.host == "upload.wikimedia.org":
            from outings_world import jpeg

            return httpx.Response(200, content=jpeg(800, 600))
        raise AssertionError(f"nobody should ask for {url}")


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
    from hub.providers import places
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from outings import hub as outings_hub

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
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(kernel_capabilities, "hub_transport", lambda: ASGITransport(app=hub_app))
    monkeypatch.setattr(outings_hub, "transport", lambda: ASGITransport(app=kernel_app))
    hub_db.engine.cache_clear()
    yield fake
    for cached in (hub_db.engine, kernel_db.engine):
        await cached().dispose()
        cached.cache_clear()
    hub_credentials.masters.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'hub'"))


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, person):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
        await connection.execute(text("delete from kernel.events where module = 'outings'"))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        c.headers[USER_HEADER] = str(person)
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
        await connection.execute(text("delete from kernel.events where module = 'outings'"))
    await kernel_db.engine().dispose()
    kernel_db.engine.cache_clear()


@pytest.fixture
async def hub_app(kernel, schema, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import capabilities as kernel_capabilities

    os.environ.setdefault("HUB_CREDENTIALS_KEY", os.urandom(32).hex())
    from hub import capabilities as hub_capabilities
    from hub import db as hub_db
    from hub.main import app as hub_app
    from kernel.main import app as kernel_app

    async with schema.begin() as connection:
        await fresh_modules(connection, "hub", "outings", fresh=["hub"])
    hub_db.engine.cache_clear()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    monkeypatch.setattr(kernel_capabilities, "hub_transport", lambda: ASGITransport(app=hub_app))
    monkeypatch.setattr(hub_capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    from outings import hub as outings_hub

    monkeypatch.setattr(outings_hub, "transport", lambda: ASGITransport(app=kernel_app))
    monkeypatch.setenv("KERNEL_URL", "http://kernel")
    yield hub_app
    await hub_db.engine().dispose()
    hub_db.engine.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'hub'"))
