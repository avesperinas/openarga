from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import current_user, install
from macros import db
from macros.main import MODULE_ID, app

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


async def fresh(connection, module: str) -> None:
    await connection.execute(text(f'drop schema if exists "{module}" cascade'))
    await connection.execute(
        text("delete from kernel.module_migrations where module = :m"), {"m": module}
    )


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://macros") as client:
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


from macros_world import world  # noqa: E402, F401 - the fixture is used by name
