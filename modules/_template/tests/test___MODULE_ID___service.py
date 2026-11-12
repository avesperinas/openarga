from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import yaml
from httpx import ASGITransport
from sqlalchemy import text

from arga_testing.contract import contract
from __MODULE_ID__ import publisher
from __MODULE_ID__.main import MODULE_ID, service

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


def test_the_manifest_says_what_this_module_is() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["id"] == MODULE_ID
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
    assert manifest["api"]["prefix"] == f"/api/{MODULE_ID}"
    assert "connectors" not in manifest


async def test_it_is_ready_once_the_kernel_provisions_it(api) -> None:
    response = await api.get("/readyz")

    assert response.status_code == 200, response.text


async def test_the_widget_is_empty_until_something_is_written_and_then_counts_it(api) -> None:
    assert (await api.get("/widgets/main")).json()["state"] == "empty"

    created = await api.post("/readings", json={"label": "peso", "value": 71.5})
    assert created.status_code == 201, created.text

    widget = (await api.get("/widgets/main")).json()
    assert widget["state"] == "ready"
    assert widget["body"] == {"value": 1, "detail": "última: peso"}
    assert [one["label"] for one in (await api.get("/readings")).json()] == ["peso"]


async def test_a_reading_reaches_the_log_once_with_its_owner(api, schema, person) -> None:
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    await asyncio.to_thread(migrate.upgrade)
    kernel_db.engine.cache_clear()
    subject = f"{MODULE_ID}-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    reading = (await api.post("/readings", json={"label": "pasos", "value": 9000})).json()
    dedup = f"reading:{reading['id']}"
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as kernel:
            async with publisher.PUBLISHER.as_module() as connection:
                await publisher.PUBLISHER.publish_pending(connection, kernel)
            async with publisher.PUBLISHER.as_module() as connection:
                await publisher.PUBLISHER.publish_pending(connection, kernel)
        async with schema.connect() as connection:
            rows = (
                await connection.execute(
                    text("select user_id, type from kernel.events where dedup_hash = :d"),
                    {"d": dedup},
                )
            ).all()
    finally:
        async with schema.begin() as connection:
            await connection.execute(
                text("delete from kernel.events where dedup_hash = :d"), {"d": dedup}
            )
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()

    assert [(row.user_id, row.type) for row in rows] == [(person, f"{MODULE_ID}.reading")]
