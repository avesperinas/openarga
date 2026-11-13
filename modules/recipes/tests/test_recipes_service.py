from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from arga_testing.contract import contract
from recipes.main import MODULE_ID, app, service
from recipes.tools import TOOLS, role_for_scopes
from recipes.widgets import RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://recipes") as client:
        yield client


async def test_it_says_it_is_alive_without_touching_the_database(bare) -> None:
    response = await bare.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": MODULE_ID}


async def test_the_manifest_says_what_this_module_is() -> None:
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


async def test_the_twelve_categories_come_with_the_module(api) -> None:
    response = await api.get("/categories")

    assert response.status_code == 200, response.text
    categories = response.json()
    assert [c["id"] for c in categories[:3]] == ["vegetable", "fruit", "protein"]
    assert len(categories) == 13
    assert all(c["emoji"] for c in categories)
    assert [c["position"] for c in categories] == sorted(c["position"] for c in categories)


async def test_a_new_installation_has_an_empty_recipe_book(api) -> None:
    response = await api.get("/recipes")

    assert response.status_code == 200
    assert response.json() == []


async def test_a_widget_that_does_not_exist_is_a_404(api) -> None:
    response = await api.get("/widgets/whatever")

    assert response.status_code == 404
    assert MODULE_ID in response.json()["detail"]


def test_the_scopes_decide_the_postgres_role() -> None:
    assert role_for_scopes({f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({f"{MODULE_ID}:read"}) == f"mod_{MODULE_ID}_read"
    assert role_for_scopes({f"{MODULE_ID}:read", f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({"training:read", "chuping:write"}) is None
    assert role_for_scopes(set()) is None


async def test_a_tool_that_does_not_exist_is_a_404(bare) -> None:
    response = await bare.post("/tools/delete_everything", json={}, headers={"x-arga-scopes": ""})

    assert response.status_code == 404
    assert MODULE_ID in response.json()["detail"]


async def test_without_a_scope_a_tool_call_never_opens_the_database(bare) -> None:
    response = await bare.post("/tools/find_recipes", json={}, headers={"x-arga-scopes": ""})

    assert response.status_code == 403
    assert MODULE_ID in response.json()["detail"]
