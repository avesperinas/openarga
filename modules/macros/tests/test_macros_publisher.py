from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import arga_contracts as contracts
from arga_tenancy import current_user
from kernel.provision import provision, role_for
from macros import publisher
from macros.main import MODULE_ID, app
from macros.tools import TOOLS
from macros.widgets import RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"
GOALS = "probe_goals"


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://macros") as client:
        yield client


async def test_it_says_it_is_alive_without_touching_the_database(bare) -> None:
    response = await bare.get("/healthz")
    assert response.json() == {"status": "ok", "module": MODULE_ID}


def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
    assert manifest["ui"]["view"] == f"/{MODULE_ID}"
    assert {tool["name"] for tool in manifest["tools"]} == set(TOOLS)
    assert {widget["id"] for widget in manifest["ui"]["widgets"]} == set(RENDERERS)
    assert set(manifest["uses"]) == contracts.PANTRY | {contracts.WEIGHT_LOG, "notify.sync"}


async def test_protein_reaches_whoever_receives_metric(api, world, schema) -> None:
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    person = current_user.get()
    subject = f"macros-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'macros'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:id, '0.1.0', true, cast(:m as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {"id": GOALS, "m": json.dumps({"receives": ["metric"]})},
        )
    await provision(GOALS)
    try:
        lentils = await world.imported("lentils", alias="dry lentils")
        response = await api.post(
            "/entries", json={"items": [{"food_id": lentils["id"], "quantity": 200, "unit": "g"}]}
        )
        assert response.status_code == 201

        def down(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/internal/users":
                return httpx.Response(200, json=[{"id": str(person)}])
            raise httpx.ConnectError("the kernel is not answering", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
            failed = await publisher.run_once(client)
        async with httpx.AsyncClient(transport=ASGITransport(app=kernel_app)) as client:
            ok = await publisher.run_once(client)
            again = await publisher.run_once(client)

        assert failed["published"] == 0 and failed["pending"] > 0
        assert ok["published"] == failed["pending"]
        assert (again["published"], again["pending"]) == (0, 0)

        async with schema.connect() as connection:
            await connection.execute(text(f"set role {role_for(GOALS)}"))
            await connection.execute(text(f"set arga.user_id = '{person}'"))
            rows = (
                await connection.execute(
                    text(f"select type, payload from {GOALS}.events where module = 'macros'")
                )
            ).all()
        assert {row.type for row in rows} == {"macros.metric"}
        points = {row.payload["metric"]["key"]: row.payload["metric"] for row in rows}
        assert points["macros.protein"]["value"] == pytest.approx(49.2)
        assert points["macros.protein"]["day"] == response.json()["day"]
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'macros'"))
            await connection.execute(
                text("delete from kernel.modules where id = :id"), {"id": GOALS}
            )
            await connection.execute(text(f"drop schema if exists {GOALS} cascade"))
            for role in (role_for(GOALS), f"{role_for(GOALS)}_read"):
                await connection.execute(
                    text(
                        "do $$ begin "
                        f"if exists (select 1 from pg_roles where rolname = '{role}') "
                        f"then execute 'drop owned by {role}'; execute 'drop role {role}'; "
                        "end if; end $$"
                    )
                )
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()
