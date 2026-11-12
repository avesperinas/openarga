from __future__ import annotations

import os
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import current_user, install
from training import db

SCHEMA = db.SCHEMA

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
    setup = install(create_async_engine(database_url))
    async with setup.begin() as connection:
        await connection.execute(text(f'create schema if not exists "{SCHEMA}"'))
    await setup.dispose()

    yield

    await db.engine().dispose()
    db.engine.cache_clear()


PERSON = UUID("00000000-0000-4000-8000-00000000a7e5")


@pytest.fixture(autouse=True)
def person(request: pytest.FixtureRequest):
    if "database_url" not in request.fixturenames:
        yield None
        return
    token = current_user.set(PERSON)
    yield PERSON
    current_user.reset(token)


@pytest.fixture(autouse=True)
def zone(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Europe/Madrid")
    return "Europe/Madrid"
