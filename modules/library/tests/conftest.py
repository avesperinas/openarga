from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_testing.module import OTHER, PERSON, fixtures
from library import db
from library.main import MODULE_ID, app

SCHEMA = db.SCHEMA
MODULES = Path(__file__).resolve().parents[2]

globals().update(fixtures(MODULE_ID, app, db))

__all__ = ["OTHER", "PERSON"]


class Hub:
    def __init__(self, client: AsyncClient, monkeypatch) -> None:
        self.client = client
        self.monkeypatch = monkeypatch

    def answer(self, handler) -> None:
        import httpx

        from hub import capabilities

        self.monkeypatch.setattr(
            capabilities, "source_transport", lambda: httpx.MockTransport(handler)
        )


@pytest.fixture
async def hub(schema, database_url, monkeypatch):
    import secrets

    from arga_testing import fresh_modules
    from hub import capabilities
    from hub import credentials as hub_credentials
    from hub import db as hub_db
    from hub.main import app as hub_app
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    monkeypatch.setenv("HUB_CREDENTIALS_KEY", os.urandom(32).hex())
    hub_credentials.masters.cache_clear()
    async with schema.begin() as connection:
        await fresh_modules(connection, MODULE_ID, "hub", fresh=["hub"])
    monkeypatch.setattr(kernel_capabilities, "hub_transport", lambda: ASGITransport(app=hub_app))
    monkeypatch.setattr(capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    hub_db.engine.cache_clear()
    app.state.client = AsyncClient(transport=ASGITransport(app=kernel_app))
    async with AsyncClient(transport=ASGITransport(app=hub_app), base_url="http://hub") as client:
        yield Hub(client, monkeypatch)
    await app.state.client.aclose()
    del app.state.client
    for cached in (hub_db.engine, kernel_db.engine):
        await cached().dispose()
        cached.cache_clear()
    hub_credentials.masters.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'hub'"))
