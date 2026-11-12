from __future__ import annotations

import os
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import current_user, install

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)

PERSON = UUID("00000000-0000-4000-8000-00000000a7e5")
OTHER = UUID("00000000-0000-4000-8000-00000000b0b0")


def fixtures(module_id: str, app: Any, db: ModuleType) -> dict[str, Any]:

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
            await fresh_modules(connection, module_id)

        yield setup

        async with setup.begin() as connection:
            await connection.execute(
                text("delete from kernel.modules where id = :id"), {"id": module_id}
            )
        await setup.dispose()
        await db.engine().dispose()
        db.engine.cache_clear()

    @pytest.fixture
    async def api(schema):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=f"http://{module_id}"
        ) as client:
            yield client

    @pytest.fixture
    async def bare():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=f"http://{module_id}"
        ) as client:
            yield client

    @pytest.fixture(autouse=True)
    def person(request: pytest.FixtureRequest):
        if "database_url" not in request.fixturenames:
            yield None
            return
        token = current_user.set(PERSON)
        yield PERSON
        current_user.reset(token)

    return {
        "database_url": database_url,
        "schema": schema,
        "api": api,
        "bare": bare,
        "person": person,
    }
