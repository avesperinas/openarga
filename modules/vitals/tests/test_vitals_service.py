from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_contracts.records import Never
from vitals import publisher, weight
from vitals.main import MODULE_ID, app
from vitals.tools import TOOLS, role_for_scopes
from vitals.widgets import RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://vitals") as client:
        yield client


async def test_it_says_it_is_alive_without_touching_the_database(bare) -> None:
    response = await bare.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": MODULE_ID}


def test_the_manifest_says_what_this_module_is() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["id"] == MODULE_ID
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
    assert manifest["api"]["prefix"] == f"/api/{MODULE_ID}"
    assert manifest["ui"]["view"] == f"/{MODULE_ID}"
    assert manifest["connectors"] == []


def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert {tool["name"] for tool in manifest["tools"]} == set(TOOLS)
    assert {widget["id"] for widget in manifest["ui"]["widgets"]} == set(RENDERERS)


def test_no_tool_deletes() -> None:
    assert not [name for name in TOOLS if name.startswith(("delete", "remove"))]


def test_the_scopes_decide_the_postgres_role() -> None:
    assert role_for_scopes({f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({f"{MODULE_ID}:read"}) == f"mod_{MODULE_ID}_read"
    assert role_for_scopes({f"{MODULE_ID}:read", f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({"training:read", "shopping:write"}) is None


async def test_without_a_scope_a_tool_call_never_opens_the_database(bare) -> None:
    response = await bare.post("/tools/log_weight", json={"kg": 80}, headers={"x-arga-scopes": ""})

    assert response.status_code == 403


async def test_a_tool_that_does_not_exist_is_a_404(bare) -> None:
    response = await bare.post("/tools/borrar_todo", json={}, headers={"x-arga-scopes": ""})

    assert response.status_code == 404


async def test_it_is_ready_once_provisioned(api, tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    monkeypatch.setenv("UI_DIST", str(tmp_path))

    response = await api.get("/readyz")

    assert response.status_code == 200
    assert response.json()["schema"] == MODULE_ID


async def test_a_weighing_reaches_the_log_with_its_owner(api, schema, monkeypatch) -> None:
    monkeypatch.setattr(publisher, "RECORDS", Never())
    monkeypatch.setattr(publisher, "METRICS", Never())
    from arga_tenancy import current_user
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    await asyncio.to_thread(migrate.upgrade)
    kernel_db.engine.cache_clear()
    person = current_user.get()
    subject = f"vitals-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'vitals'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    try:
        await publish_and_check(api, schema, person, kernel_app)
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'vitals'"))
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()


async def publish_and_check(api, schema, person, kernel_app) -> None:
    created = await api.post("/weight", json={"kg": 81.3, "day": "2026-09-20"})
    assert created.status_code == 201

    def down(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/users":
            return httpx.Response(200, json=[{"id": str(person)}])
        raise httpx.ConnectError("el kernel no contesta", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        failed = await publisher.run_once(client)
    async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as client:
        ok = await publisher.run_once(client)
        again = await publisher.run_once(client)

    assert failed["published"] == 0 and failed["pending"] == 1
    assert ok["published"] == 1 and again == {"published": 0, "pending": 0}
    async with schema.connect() as connection:
        events = (
            await connection.execute(
                text("select type, user_id, payload from kernel.events where module = 'vitals'")
            )
        ).all()
    assert [(row.type, row.user_id) for row in events] == [("vitals.weight", person)]
    assert events[0].payload["kg"] == 81.3
    assert events[0].payload["body_weight"] == {
        "id": events[0].payload["weight_id"],
        "day": "2026-09-20",
        "kg": 81.3,
    }


async def test_what_was_weighed_before_is_published_with_the_contract_once(api, schema) -> None:
    await api.post("/weight", json={"kg": 80.1, "day": "2026-09-01"})
    await api.post("/weight", json={"kg": 79.9, "day": "2026-09-08"})
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_vitals"'))
        await connection.execute(text("delete from vitals.vitals_outbox"))

    for _ in range(2):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_vitals"'))
            await weight.backfill(connection)

    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_vitals"'))
        payloads = (
            (await connection.execute(text("select payload from vitals.vitals_outbox order by id")))
            .scalars()
            .all()
        )
    assert sorted(one["body_weight"]["kg"] for one in payloads) == [79.9, 80.1]
