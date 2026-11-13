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


async def test_each_area_has_its_own_map_folder_and_shares_the_fonts(
    bare, tmp_path, monkeypatch
) -> None:
    (tmp_path / "index.html").write_text("<div id=root></div>")
    folder = tmp_path / "map" / "pamplona"
    folder.mkdir(parents=True)
    (tmp_path / "map" / "VERSION").write_text("abc123\n")
    (folder / "region.pmtiles").write_bytes(b"region")
    (folder / "relief-near.json").write_text("{}")
    (tmp_path / "map" / "fonts").mkdir()
    (tmp_path / "map" / "fonts" / "0-255.pbf").write_bytes(b"font")
    monkeypatch.setenv("UI_DIST", str(tmp_path))

    region = await bare.get("/outings/map/v-abc123/pamplona/region.pmtiles")
    relief = await bare.get("/outings/map/v-abc123/pamplona/relief-near.json")
    font = await bare.get("/outings/map/v-abc123/pamplona/fonts/0-255.pbf")
    other = await bare.get("/outings/map/v-abc123/munich/region.pmtiles")
    sneaky = await bare.get("/outings/map/v-abc123/pamplona/%2E%2E/%2E%2E/index.html")

    assert region.content == b"region"
    assert relief.status_code == 200 and font.content == b"font"
    assert other.status_code == 404 and sneaky.status_code == 404


async def test_the_area_says_its_names_boxes_and_whether_it_has_a_map(
    bare, area, tmp_path, monkeypatch
) -> None:
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "map" / "pamplona").mkdir(parents=True)
    (tmp_path / "map" / "pamplona" / "region.pmtiles").write_bytes(b"x")
    monkeypatch.setenv("UI_DIST", str(tmp_path))

    default = (await bare.get("/area")).json()
    asked = (await bare.get("/area", headers={"x-arga-area": "munich"})).json()

    assert default["id"] == area.id and default["near"] == area.near.name
    assert default["region_box"] == list(area.region.box)
    assert default["map"] is (area.id == "pamplona")
    assert asked["id"] == "munich" and asked["map"] is False and asked["relief"] is None
    assert default["relief"] == (area.map.relief.attribution if area.map.relief else None)
