from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from arga_testing.contract import contract
from insights.main import MODULE_ID, app, service
from insights.tools import TOOLS, role_for_scopes
from insights.widgets import RENDERERS

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))


@pytest.fixture
async def bare():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://insights") as client:
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
    assert manifest["ui"]["family"] == "companion"
    assert manifest["ui"]["badge"] == f"/api/{MODULE_ID}/badge"


def test_what_the_manifest_declares_is_what_the_module_serves() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert {tool["name"] for tool in manifest["tools"]} == set(TOOLS)
    assert {widget["id"] for widget in manifest["ui"]["widgets"]} == set(RENDERERS)


def test_insights_only_writes_in_insights() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    writing = {t["name"] for t in manifest["tools"] if t["scope"] == "insights:write"}

    assert writing == {
        "publish_insight",
        "rate_insight",
        "reply",
        "publish_pill",
        "publish_facts",
        "publish_picks",
        "ask_question",
        "propose_trait",
        "note_taste",
    }


def test_the_scopes_decide_the_postgres_role() -> None:
    assert role_for_scopes({f"{MODULE_ID}:write"}) == f"mod_{MODULE_ID}"
    assert role_for_scopes({f"{MODULE_ID}:read"}) == f"mod_{MODULE_ID}_read"
    assert role_for_scopes({"training:read", "recipes:write"}) is None


async def test_without_a_scope_a_tool_call_never_opens_the_database(bare) -> None:
    response = await bare.post("/tools/get_profile", json={}, headers={"x-arga-scopes": ""})

    assert response.status_code == 403
