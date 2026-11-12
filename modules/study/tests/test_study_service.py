from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from arga_testing.contract import contract
from arga_widgets import BadBody, validate
from study import widgets
from study.main import MODULE_ID, app, service

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


@pytest.fixture
async def api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://study") as client:
        yield client


async def test_it_says_it_is_alive_without_touching_the_database(api) -> None:
    response = await api.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": MODULE_ID}


async def test_it_is_not_ready_without_the_app_built(api, schema, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UI_DIST", str(tmp_path))

    response = await api.get("/readyz")

    assert response.status_code == 503
    assert "app" in response.json()["detail"]


async def test_it_is_ready_once_its_schema_exists(api, schema, tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    monkeypatch.setenv("UI_DIST", str(tmp_path))

    response = await api.get("/readyz")

    assert response.status_code == 200, response.text
    assert response.json()["schema"] == MODULE_ID


def test_the_prefix_of_its_api_is_what_the_manifest_declares() -> None:
    manifest = yaml.safe_load((Path(__file__).resolve().parents[1] / "manifest.yaml").read_text())

    assert manifest["api"]["prefix"] == f"/api/{MODULE_ID}"
    assert manifest["database"]["schema"] == MODULE_ID
    assert manifest["database"]["role"] == f"mod_{MODULE_ID}"


async def test_each_widget_answers_the_common_envelope_when_there_is_nothing(api, schema) -> None:
    for widget_id in ("upnext", "progress", "average"):
        response = await api.get(f"/widgets/{widget_id}")

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) >= {"state", "updated_at", "body"}
        assert body["state"] == "empty"
        assert body["body"]["detail"]


async def test_a_widget_it_does_not_have_is_a_404_and_not_a_500(api, schema) -> None:
    response = await api.get("/widgets/no-existe")

    assert response.status_code == 404
    assert "no-existe" in response.json()["detail"]


def test_the_widget_bodies_match_the_kinds_the_manifest_declares() -> None:
    manifest = yaml.safe_load((Path(__file__).resolve().parents[1] / "manifest.yaml").read_text())
    declared = {widget["id"]: widget["kind"] for widget in manifest["ui"]["widgets"]}

    assert declared == widgets.KINDS
    assert set(declared) == set(widgets.RENDERERS)
    with pytest.raises(BadBody):
        validate("progress", {"series": [1, 2, 3]})


def test_the_manifest_declares_each_widget_where_it_really_serves() -> None:
    manifest = yaml.safe_load((Path(__file__).resolve().parents[1] / "manifest.yaml").read_text())
    for widget in manifest["ui"]["widgets"]:
        assert widget["endpoint"] == f"/api/{MODULE_ID}/widgets/{widget['id']}"
        assert set(widget["sizes"]) <= {"1x1", "2x1", "4x1", "1x2", "2x2", "2x4", "4x2", "4x4"}
        assert widget["link"].startswith(f"/{MODULE_ID}")


def test_the_manifest_declares_every_tool_it_serves() -> None:
    from study import tools

    manifest = yaml.safe_load((Path(__file__).resolve().parents[1] / "manifest.yaml").read_text())
    declared = {tool["name"]: tool["scope"] for tool in manifest["tools"]}

    assert set(declared) == set(tools.TOOLS)
    assert len(declared) == 30
    assert {name for name, scope in declared.items() if scope == "study:read"} == {
        "get_courses",
        "get_course",
        "get_week",
        "get_grades",
        "find_notes",
        "get_note",
    }
