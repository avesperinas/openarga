from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from travel_kit import BRUGES, LILLE, make_trip, stay

from arga_contracts.records import Never
from arga_testing.contract import contract
from arga_widgets import validate
from travel import publisher, travel
from travel.main import MODULE_ID, app, service
from travel.tools import TOOLS, role_for_scopes
from travel.widgets import KINDS, RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://travel") as client:
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
    assert manifest["uses"] == [
        "places.search",
        "places.photo",
        "maps.tile",
        "routes.directions",
        "places.nearby",
        "weather.forecast",
        "weather.climate",
        "fx.rate",
    ]


def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert {tool["name"] for tool in manifest["tools"]} == set(TOOLS)
    assert len(TOOLS) == 58
    assert {widget["id"] for widget in manifest["ui"]["widgets"]} == set(RENDERERS)
    assert {w["id"]: w["kind"] for w in manifest["ui"]["widgets"]} == KINDS


def test_the_scopes_decide_the_postgres_role() -> None:
    assert role_for_scopes({f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({f"{MODULE_ID}:read"}) == f"mod_{MODULE_ID}_read"
    assert role_for_scopes({"training:read", "recipes:write"}) is None


async def test_the_map_geometries_are_served_whole_for_the_gateway_to_compress(bare) -> None:
    response = await bare.get("/travel/geo/countries.json", headers={"accept-encoding": "gzip"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["type"] == "Topology"
    assert (await bare.get("/travel/geo/manifest.yaml")).status_code == 404


async def test_the_suggested_concepts_are_those_of_the_sheet(bare) -> None:
    concepts = (await bare.get("/concepts")).json()

    assert list(concepts) == ["transport", "lodging", "other"]
    assert "Gasolina y parking" in concepts["transport"]


async def test_every_widget_answers_its_kind_empty_and_full(api) -> None:
    for widget_id in KINDS:
        body = (await api.get(f"/widgets/{widget_id}")).json()
        assert body["state"] == "empty", widget_id
    trip = await make_trip(api, starts="2024-04-10", ends="2024-04-12")
    await stay(api, trip["id"], BRUGES, "2024-04-10", "2024-04-12")
    soon = (travel.today() + timedelta(days=30)).isoformat()
    later = await make_trip(api, "Lille", soon, soon, status="plan")
    await stay(api, later["id"], LILLE, soon, soon)

    for widget_id, kind in KINDS.items():
        body = (await api.get(f"/widgets/{widget_id}")).json()
        assert body["state"] == "ready", widget_id
        validate(kind, body["body"])
    countries = (await api.get("/widgets/countries")).json()["body"]
    assert (countries["value"], countries["detail"]) == (1, "1 de 44 de Europa")
    last = (await api.get("/widgets/last_trip")).json()["body"]["events"][0]
    assert (last["title"], last["detail"]) == ("Flandes", "2 noches · Brujas")
    upcoming = (await api.get("/widgets/next_trip")).json()["body"]["events"][0]
    assert (upcoming["title"], upcoming["detail"]) == ("Lille", "plan · 1 día · Lille")

    await api.put(f"/trips/{trip['id']}/archived", json={"archived": True})
    assert (await api.get("/widgets/last_trip")).json()["state"] == "empty"
    assert (await api.get("/widgets/countries")).json()["body"]["value"] == 1


async def test_a_saved_trip_reaches_the_log_once_with_its_owner(api, schema, monkeypatch) -> None:
    monkeypatch.setattr(publisher, "RECORDS", Never())
    monkeypatch.setattr(publisher, "METRICS", Never())
    from arga_tenancy import current_user
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    await asyncio.to_thread(migrate.upgrade)
    kernel_db.engine.cache_clear()
    person = current_user.get()
    subject = f"travel-tests-{person}"
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'travel'"))
        await connection.execute(
            text("insert into kernel.users (id, subject) values (:id, :s) on conflict do nothing"),
            {"id": person, "s": subject},
        )
    try:
        trip = await make_trip(api, travellers=2)

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
        assert ok["published"] == 1 and again == {"published": 0, "pending": 0, "more": 0}
        async with schema.connect() as connection:
            events = (
                await connection.execute(
                    text("select type, user_id, payload from kernel.events where module = 'travel'")
                )
            ).all()
        assert [(row.type, row.user_id) for row in events] == [("travel.trip", person)]
        assert events[0].payload["trip_id"] == trip["id"]
        assert events[0].payload["travellers"] == 2
    finally:
        async with schema.begin() as connection:
            await connection.execute(text("delete from kernel.events where module = 'travel'"))
            await connection.execute(
                text("delete from kernel.users where subject = :s"), {"s": subject}
            )
        await kernel_db.engine().dispose()
        kernel_db.engine.cache_clear()
