from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import current_user, install
from study import db
from study.main import MODULE_ID, app

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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://study") as client:
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


@pytest.fixture
async def notebook(schema, database_url, monkeypatch):
    import asyncio
    import secrets

    from arga_testing import fresh_modules
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from notebook import db as notebook_db
    from notebook.main import app as notebook_app

    kernel_db.engine.cache_clear()
    notebook_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    async with schema.begin() as connection:
        await fresh_modules(connection, MODULE_ID, "notebook", fresh=["notebook"])
    monkeypatch.setattr(
        kernel_capabilities, "module_transport", lambda: ASGITransport(app=notebook_app)
    )
    app.state.client = AsyncClient(transport=ASGITransport(app=kernel_app))
    async with AsyncClient(
        transport=ASGITransport(app=notebook_app), base_url="http://notebook"
    ) as client:
        yield client
    await app.state.client.aclose()
    app.state.client = None
    for cached in (kernel_db.engine, notebook_db.engine):
        await cached().dispose()
        cached.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'notebook'"))
