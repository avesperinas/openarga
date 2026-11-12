from __future__ import annotations

import os
from pathlib import Path

import pytest
from goals_people import PERSON
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import current_user, install
from goals import db
from goals.main import MODULE_ID, app

SCHEMA = db.SCHEMA
MODULES = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)


@pytest.fixture(scope="session")
def database_url() -> str:
    from kernel import db as kernel_db
    from kernel import migrate

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    db.engine.cache_clear()
    kernel_db.engine.cache_clear()
    migrate.upgrade()
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://goals") as client:
        yield client


@pytest.fixture(autouse=True)
def person(request: pytest.FixtureRequest):
    if "database_url" not in request.fixturenames:
        yield None
        return
    token = current_user.set(PERSON)
    yield PERSON
    current_user.reset(token)
