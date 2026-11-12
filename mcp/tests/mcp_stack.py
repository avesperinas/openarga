from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import current_user, install

REPO = Path(__file__).resolve().parents[2]
PERSON = UUID("00000000-0000-4000-8000-00000000a7e5")
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)


class Hosts(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[str, httpx.AsyncBaseTransport]):
        self.routes = routes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.routes[request.url.host].handle_async_request(request)


@pytest.fixture
def settings():
    from arga_mcp.main import Settings

    return Settings()


@pytest.fixture
def migrated() -> None:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    from kernel import db as kernel_db
    from kernel import migrate
    from shopping import db as shopping_db
    from training import db as training_db

    for cached in (
        kernel_db.engine,
        kernel_db.session_factory,
        training_db.engine,
        shopping_db.engine,
    ):
        cached.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def stack(migrated):
    from arga_testing import fresh_modules
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app
    from shopping import db as shopping_db
    from shopping.main import app as shopping_app
    from training import db as training_db
    from training import seed
    from training.main import app as training_app

    root = REPO / "modules"
    setup = install(create_async_engine(TEST_DATABASE_URL))
    person = current_user.set(PERSON)
    mine = ("training", "shopping")
    async with setup.begin() as connection:
        await fresh_modules(connection, *mine, root=root)
        await connection.execute(text('set local role "mod_training"'))
        await seed.seed(connection)

    client = httpx.AsyncClient(
        transport=Hosts(
            {
                "kernel": httpx.ASGITransport(app=kernel_app),
                "training": httpx.ASGITransport(app=training_app),
                "shopping": httpx.ASGITransport(app=shopping_app),
            }
        )
    )
    current_user.reset(person)
    yield client

    await client.aclose()
    async with setup.begin() as connection:
        await connection.execute(
            text("delete from kernel.modules where id = any(:ids)"), {"ids": list(mine)}
        )
    await setup.dispose()
    await kernel_db.engine().dispose()
    await training_db.engine().dispose()
    await shopping_db.engine().dispose()
    for cached in (
        kernel_db.engine,
        kernel_db.session_factory,
        training_db.engine,
        shopping_db.engine,
    ):
        cached.cache_clear()
