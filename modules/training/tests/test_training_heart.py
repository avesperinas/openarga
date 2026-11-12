from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import install
from training import main as training_main

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
async def apps(database_url, person, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import capabilities as kernel_capabilities
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app
    from vitals import db as vitals_db
    from vitals.main import app as vitals_app

    kernel_db.engine.cache_clear()
    vitals_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", secrets.token_hex(16))
    monkeypatch.setenv("KERNEL_URL", "http://kernel")
    engine = install(create_async_engine(database_url))
    async with engine.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'training'"))
        await fresh_modules(connection, "training", "vitals", root=ROOT)
    monkeypatch.setattr(
        kernel_capabilities, "module_transport", lambda: ASGITransport(app=vitals_app)
    )
    monkeypatch.setattr(training_main, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    async with AsyncClient(
        transport=ASGITransport(app=training_main.app), base_url="http://training"
    ) as client:
        yield engine, client
    async with engine.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'training'"))
        await connection.execute(
            text("delete from kernel.events where source = 'google_health' and type = :t"),
            {"t": "health.heart"},
        )
    for cached in (kernel_db.engine, vitals_db.engine):
        await cached().dispose()
        cached.cache_clear()
    await engine.dispose()


async def published(
    engine, person, module: str, kind: str, payload: dict, source="app", ts=None
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash, user_id)"
                " values (coalesce(:ts, now()), :m, :source, :type, cast(:payload as jsonb),"
                " :dedup, :user)"
            ),
            {
                "ts": ts,
                "m": module,
                "source": source,
                "type": kind,
                "payload": json.dumps(payload),
                "dedup": f"{kind}:{uuid.uuid4()}",
                "user": person,
            },
        )


async def test_a_session_shows_its_heart_from_vitals(apps, person) -> None:
    engine, training = apps
    session = str(uuid.uuid4())
    start = datetime(2026, 9, 14, 17, 0, tzinfo=UTC)
    await published(
        engine,
        person,
        "hub",
        "health.heart",
        {
            "date": "2026-09-14",
            "step": 1,
            "buckets": [
                {"minute": 19 * 60 + m, "min": 120, "avg": 120, "max": 120} for m in range(0, 45)
            ],
        },
        source="google_health",
        ts=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
    )
    await published(
        engine,
        person,
        "training",
        "training.workout",
        {
            "workout": {
                "id": f"training:session:{session}",
                "kind": "strength",
                "name": "Push",
                "start": start.isoformat(),
                "end": (start + timedelta(minutes=40)).isoformat(),
                "tz": "Europe/Madrid",
                "href": f"/training/session/{session}",
                "band_id": None,
                "marks": [],
                "removed": False,
            }
        },
    )

    found = await training.get("/heart", params={"id": f"training:session:{session}"})
    missing = await training.get("/heart", params={"id": f"training:activity:{uuid.uuid4()}"})
    refused = await training.get("/heart", params={"id": "other:session:1"})

    assert found.status_code == 200, found.text
    body = found.json()
    assert (body["found"], body["minutes"], body["avg"], body["source"]) == (True, 40, 120, "day")
    assert len(body["zones"]) == 5
    assert missing.json()["found"] is False
    assert refused.status_code == 422
