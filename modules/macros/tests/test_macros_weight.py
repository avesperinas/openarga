from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from macros_world import Down, Router
from sqlalchemy import text

MODULES = Path(__file__).resolve().parents[2]


@pytest.fixture
async def scale(schema, database_url, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from macros.main import app
    from vitals import db as vitals_db
    from vitals import publisher
    from vitals.main import app as vitals_app

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'vitals'"))
        await fresh_modules(connection, "vitals", "macros", fresh=["vitals"])
    monkeypatch.setattr(
        kernel_capabilities, "module_transport", lambda: Router({"vitals": vitals_app})
    )
    vitals_db.engine.cache_clear()
    to_kernel = AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel")
    app.state.client = to_kernel

    async def publish() -> None:
        async with vitals_db.engine().begin() as connection:
            await connection.execute(text('set local role "mod_vitals"'))
            await publisher.publish_pending(connection, to_kernel)

    yield publish
    await to_kernel.aclose()
    app.state.client = None
    for cached in (kernel_db.engine, vitals_db.engine):
        await cached().dispose()
        cached.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'vitals'"))


async def test_a_weight_typed_in_macros_is_kept_by_the_keeper_and_read_back(api, scale) -> None:
    logged = await api.post("/weight", json={"kg": 80.4, "day": "2026-09-22"})
    assert logged.status_code == 200, logged.text
    assert logged.json()["latest"] == {"day": "2026-09-22", "kg": 80.4}

    await scale()
    found = (await api.get("/weight")).json()

    assert found["days"] == [{"day": "2026-09-22", "kg": 80.4}]

    await api.post("/weight", json={"kg": 80.0, "day": "2026-09-22"})
    await scale()
    found = (await api.get("/weight")).json()
    assert found["days"] == [{"day": "2026-09-22", "kg": 80.0}]


async def test_with_the_keeper_down_nothing_is_logged_and_it_says_so(
    api, scale, monkeypatch
) -> None:
    from kernel import capabilities as kernel_capabilities

    monkeypatch.setattr(kernel_capabilities, "module_transport", lambda: Down())

    refused = await api.post("/weight", json={"kg": 61.3, "day": "2026-09-25"})

    assert refused.status_code == 503
    assert "Vitals is not answering" in refused.json()["detail"]
    assert "Error" not in refused.json()["detail"]
    found = (await api.get("/weight")).json()
    assert "2026-09-25" not in [one["day"] for one in found["days"]]
