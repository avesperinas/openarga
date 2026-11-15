from __future__ import annotations

import os
import secrets

import pytest
from httpx import ASGITransport
from insights_hub import settle
from sqlalchemy import text

from insights import passes
from insights.main import as_role


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def hub_app(migrated, schema, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    os.environ.setdefault("HUB_CREDENTIALS_KEY", os.urandom(32).hex())
    from hub import capabilities as hub_capabilities
    from hub import db as hub_db
    from hub.main import app as hub_main
    from insights import hub as insights_hub
    from kernel.main import app as kernel_app

    async with schema.begin() as connection:
        await fresh_modules(connection, "hub", "insights", fresh=["hub"])
    hub_db.engine.cache_clear()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    monkeypatch.setenv("KERNEL_URL", "http://kernel")
    monkeypatch.setattr(kernel_capabilities, "hub_transport", lambda: ASGITransport(app=hub_main))
    monkeypatch.setattr(hub_capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    monkeypatch.setattr(insights_hub, "transport", lambda: ASGITransport(app=kernel_app))
    yield hub_main
    for cached in (hub_db.engine, kernel_db.engine):
        await cached().dispose()
        cached.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'hub'"))


async def test_a_pass_runs_on_ai_run_and_its_end_is_read_with_ai_status(api, hub_app) -> None:
    answer = await passes.ask("morning:2026-10-13", "Say hello.")
    again = await passes.ask("morning:2026-10-13", "Say hello.")
    ended = await settle_after_asking("morning:2026-10-13")

    assert answer == {"outcome": "queued", "status": "done"}
    assert again == {"outcome": "queued", "status": "repeated"}
    assert ended is not None and ended.outcome == "ok" and "fake" in (ended.ran_with or "")


async def settle_after_asking(key: str):
    async with as_role("mod_insights") as connection:
        await connection.execute(
            text(
                "insert into insights.insights_run (kind, key, outcome) "
                "values ('morning', :key, 'queued')"
            ),
            {"key": key},
        )
    assert await settle() == 1
    async with as_role("mod_insights") as connection:
        return (await connection.execute(passes.FINISHED, {"key": f"insights:{key}"})).first()
