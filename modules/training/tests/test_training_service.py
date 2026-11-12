from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from training.main import MODULE_ID, app

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Training</title>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "manifest.webmanifest").write_text("{}")
    monkeypatch.setenv("UI_DIST", str(tmp_path))
    return tmp_path


@pytest.fixture
async def api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as client:
        yield client


async def test_it_says_it_is_alive_without_touching_the_database(api) -> None:
    response = await api.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": MODULE_ID}


async def test_it_is_ready_once_its_schema_exists_and_the_app_is_built(api, schema, built) -> None:
    response = await api.get("/readyz")

    assert response.status_code == 200, response.text


async def test_it_is_not_ready_without_the_app(api, schema, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UI_DIST", str(tmp_path / "vacio"))

    response = await api.get("/readyz")

    assert response.status_code == 503
    assert "construida" in response.json()["detail"]


async def test_the_app_is_served_under_its_view(api, built) -> None:
    index = await api.get("/training/")
    asset = await api.get("/training/assets/app-abc123.js")
    manifest = await api.get("/training/manifest.webmanifest")

    assert index.status_code == 200 and "<title>Training</title>" in index.text
    assert index.headers["cache-control"] == "no-cache"
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert manifest.status_code == 200
    assert manifest.headers["cache-control"] == "no-cache"


async def test_a_screen_of_the_app_answers_with_the_app(api, built) -> None:
    response = await api.get("/training/sesion/42")

    assert response.status_code == 200
    assert "<title>Training</title>" in response.text


async def test_a_missing_file_is_a_404_and_not_the_page(api, built) -> None:
    response = await api.get("/training/assets/app-viejo.js")

    assert response.status_code == 404


async def test_nothing_outside_the_build_is_served(api, built) -> None:
    (built.parent / "secreto.txt").write_text("fuera del build")

    response = await api.get("/training/..%2Fsecreto.txt")

    assert "fuera del build" not in response.text


def test_the_manifest_declares_where_it_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["api"]["prefix"] == f"/api/{MODULE_ID}"
    assert manifest["ui"]["view"] == f"/{MODULE_ID}"
    assert manifest["database"] == {"schema": MODULE_ID, "role": f"mod_{MODULE_ID}", "reads": []}
