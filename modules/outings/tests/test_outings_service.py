from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from arga_testing.contract import contract
from outings.main import MODULE_ID, app, service
from outings.tools import TOOLS, role_for_scopes
from outings.widgets import RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://outings") as client:
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
    assert manifest["ui"]["family"] == "wellbeing"
    assert manifest["connectors"] == []


def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert {tool["name"] for tool in manifest.get("tools") or []} == set(TOOLS)
    assert {widget["id"] for widget in manifest["ui"].get("widgets") or []} == set(RENDERERS)


def test_the_scopes_decide_the_postgres_role() -> None:
    assert role_for_scopes({f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({f"{MODULE_ID}:read"}) == f"mod_{MODULE_ID}_read"
    assert role_for_scopes({f"{MODULE_ID}:read", f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({"travel:read", "shopping:write"}) is None


async def test_a_tool_that_does_not_exist_is_a_404(bare) -> None:
    response = await bare.post("/tools/vaciar_todo", json={}, headers={"x-arga-scopes": ""})

    assert response.status_code == 404


async def test_the_map_files_of_this_version_are_cached_for_good(
    bare, tmp_path, monkeypatch
) -> None:
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "map").mkdir()
    (tmp_path / "map" / "VERSION").write_text("abc123\n")
    (tmp_path / "map" / "comarca.pmtiles").write_bytes(b"0123456789")
    (tmp_path / "secreto.txt").write_text("no")
    monkeypatch.setenv("UI_DIST", str(tmp_path))

    now = await bare.get("/outings/map/v-abc123/comarca.pmtiles", headers={"range": "bytes=2-4"})
    before = await bare.get("/outings/map/v-0ld000/comarca.pmtiles")
    outside = await bare.get("/outings/map/v-abc123/%2E%2E/secreto.txt")
    missing = await bare.get("/outings/map/v-abc123/navarra.pmtiles")

    assert now.status_code == 206 and now.content == b"234"
    assert "immutable" in now.headers["cache-control"]
    assert before.status_code == 200 and before.headers["cache-control"] == "no-cache"
    assert outside.status_code == 404
    assert missing.status_code == 404
