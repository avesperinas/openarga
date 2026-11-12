from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_agenda import check_event
from arga_contracts.records import Never
from arga_tenancy import current_user
from arga_testing.contract import contract
from goals import publisher
from goals.common import today
from goals.main import MODULE_ID, app, service
from goals.tools import TOOLS
from goals.widgets import RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://goals") as client:
        yield client


async def test_it_says_it_is_alive_without_touching_the_database(bare) -> None:
    response = await bare.get("/healthz")
    assert response.json() == {"status": "ok", "module": MODULE_ID}


def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
    from goals.main import UI_ROOT

    assert manifest["ui"]["view"] == UI_ROOT == "/goals"
    assert manifest["ui"]["family"] == "goals"
    assert {tool["name"] for tool in manifest["tools"]} == set(TOOLS)
    assert {widget["id"] for widget in manifest["ui"]["widgets"]} == set(RENDERERS)


async def test_what_goals_writes_reaches_the_log_and_the_calendar(api, schema, monkeypatch) -> None:
    monkeypatch.setattr(publisher, "RECORDS", Never())
    monkeypatch.setattr(publisher, "HISTORY", {current_user.get()})
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    person = current_user.get()
    subject = f"goals-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'goals'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    try:
        home = next(one for one in (await api.get("/categories")).json() if one["name"] == "Casa")
        due = (today() + timedelta(days=4)).isoformat()
        timed = await api.post(
            "/tasks",
            json={
                "category_id": home["id"],
                "title": "Fontanero",
                "due_on": due,
                "due_time": "18:30",
            },
        )
        undated = await api.post("/tasks", json={"category_id": home["id"], "title": "Trastero"})
        assert timed.status_code == undated.status_code == 201
        await api.post(f"/tasks/{timed.json()['id']}/done")

        def down(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/internal/users":
                return httpx.Response(200, json=[{"id": str(person)}])
            raise httpx.ConnectError("el kernel no contesta", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
            failed = await publisher.run_once(client)
        async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as client:
            ok = await publisher.run_once(client)
            again = await publisher.run_once(client)

        assert failed["published"] == 0 and failed["pending"] == 3
        assert ok["published"] == 3 and again == {"published": 0, "pending": 0, "more": 0}
        async with schema.connect() as connection:
            events = (
                await connection.execute(
                    text(
                        "select type, user_id, payload from kernel.events "
                        "where module = 'goals' order by ts"
                    )
                )
            ).all()
        assert sorted((row.type, row.user_id) for row in events) == [
            ("goals.metric", person),
            ("goals.task", person),
            ("goals.task", person),
        ]
        figure = next(row.payload for row in events if row.type == "goals.metric")
        assert figure["metric"]["key"] == "goals.tasks_done" and figure["metric"]["value"] == 1
        created, finished = (check_event(row.payload) for row in events if row.type == "goals.task")
        assert created["title"] == "Fontanero" and created["status"] == "confirmed"
        assert created["start"] == created["end"] and created["start"].startswith(f"{due}T18:30")
        assert created["href"] == f"/goals/tarea/{timed.json()['id']}"
        assert finished["status"] == "cancelled" and finished["uid"] == created["uid"]
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'goals'"))
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()
