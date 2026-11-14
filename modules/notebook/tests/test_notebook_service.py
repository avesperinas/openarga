from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_contracts.records import Never
from arga_testing.contract import contract
from notebook import publisher
from notebook.main import MODULE_ID, app, app_service
from notebook.tools import TOOLS
from notebook.widgets import RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(app_service, MANIFEST))


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://notebook") as client:
        yield client


def test_the_manifest_says_what_this_module_is() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["id"] == MODULE_ID
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
    assert manifest["api"]["prefix"] == f"/api/{MODULE_ID}"
    assert manifest["ui"]["view"] == f"/{MODULE_ID}"
    assert manifest["ui"]["family"] == "growth"
    assert manifest["connectors"] == []


def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert {tool["name"] for tool in manifest["tools"]} == set(TOOLS)
    assert {widget["id"] for widget in manifest["ui"]["widgets"]} == set(RENDERERS)


def test_no_tool_deletes_or_rewrites_a_whole_note() -> None:
    for name in TOOLS:
        assert not any(word in name for word in ("delete", "remove", "trash", "overwrite"))
    manifest = yaml.safe_load(MANIFEST.read_text())
    writes = {t["name"] for t in manifest["tools"] if t["scope"].endswith(":write")}
    assert writes == {
        "create_note",
        "append_to_note",
        "edit_note",
        "replace_section",
        "set_properties",
        "add_to_daily_note",
        "move_note",
    }


async def test_every_tool_publishes_the_shape_of_its_arguments(bare) -> None:
    listed = (await bare.get("/tools")).json()

    assert {tool["name"] for tool in listed} == set(TOOLS)
    assert all(tool["input_schema"]["type"] == "object" for tool in listed)


async def test_a_change_reaches_the_log_once_with_its_owner_and_without_the_text(
    api, schema, monkeypatch
) -> None:
    from arga_tenancy import current_user
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    await asyncio.to_thread(migrate.upgrade)
    kernel_db.engine.cache_clear()
    for every in ("MIRROR", "DIGEST", "EXPORT", "NOTIFY"):
        monkeypatch.setattr(publisher, every, Never())
    person = current_user.get()
    subject = f"notebook-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'notebook'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    try:
        created = await api.post("/notes", json={"title": "Secret", "content": "what I know"})
        assert created.status_code == 201, created.text

        def down(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/internal/users":
                return httpx.Response(200, json=[{"id": str(person)}])
            raise httpx.ConnectError("the kernel does not answer", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
            failed = await publisher.run_once(client)
        async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as client:
            ok = await publisher.run_once(client)
            again = await publisher.run_once(client)

        assert failed["published"] == 0 and failed["pending"] == 1
        assert ok["published"] == 1 and again["published"] == 0 and again["pending"] == 0
        async with schema.connect() as connection:
            events = (
                await connection.execute(
                    text(
                        "select type, user_id, payload from kernel.events where module = 'notebook'"
                    )
                )
            ).all()
        assert [(row.type, row.user_id) for row in events] == [("notebook.note_changed", person)]
        assert events[0].payload["note_id"] == created.json()["id"]
        assert "what I know" not in str(events[0].payload)
        assert "Secreto" not in str(events[0].payload)
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'notebook'"))
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()
