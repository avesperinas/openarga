from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from arga_testing.contract import contract
from arga_widgets import validate
from hub import catalogue
from hub.main import MODULE_ID, app, service
from hub.tools import TOOLS
from hub.widgets import RENDERERS

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "manifest.yaml"
MANIFEST = yaml.safe_load(MANIFEST_PATH.read_text())

globals().update(contract(service, MANIFEST_PATH))


async def test_it_says_it_is_alive_without_touching_the_database() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://c") as client:
        response = await client.get("/healthz")

    assert response.json() == {"status": "ok", "module": MODULE_ID}


@pytest.fixture
def built(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<title>Hub</title>")
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)")
    (tmp_path / "icon.svg").write_text("<svg/>")
    monkeypatch.setenv("UI_DIST", str(tmp_path))
    return tmp_path


async def test_it_is_ready_once_its_schema_exists_and_its_app_is_built(api, built) -> None:
    response = await api.get("/readyz")

    assert response.status_code == 200, response.text
    assert response.json()["schema"] == MODULE_ID


async def test_without_its_app_built_it_is_not_ready(api, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UI_DIST", str(tmp_path / "no-esta"))

    response = await api.get("/readyz")

    assert response.status_code == 503
    assert "no está construida" in response.json()["detail"]


async def test_the_app_opens_at_its_view_and_any_screen_is_the_app(built) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://c") as client:
        root = await client.get("/hub")
        screen = await client.get("/hub/bitvavo")
        asset = await client.get("/hub/assets/index-abc.js")
        outside = await client.get("/hub/%2e%2e/%2e%2e/pyproject.toml")

    assert root.text == screen.text == "<title>Hub</title>"
    assert "immutable" in asset.headers["cache-control"]
    assert outside.status_code == 404


def test_the_manifest_is_the_one_the_gateway_and_the_kernel_expect() -> None:
    from kernel.manifests import Manifest

    manifest = Manifest.model_validate(MANIFEST)

    assert manifest.api.prefix == f"/api/{MODULE_ID}"
    assert manifest.ui.view == f"/{MODULE_ID}"
    assert manifest.connectors == []


def test_every_widget_and_tool_in_the_manifest_is_served_and_nothing_else() -> None:
    assert {widget["id"] for widget in MANIFEST["ui"]["widgets"]} == set(RENDERERS)
    assert {tool["name"] for tool in MANIFEST["tools"]} == set(TOOLS)


def test_the_only_write_tool_records_a_portfolio() -> None:
    writes = {tool["name"] for tool in MANIFEST["tools"] if tool["scope"] == f"{MODULE_ID}:write"}
    assert writes == {"record_portfolio"}


async def test_the_catalogue_comes_in_its_categories_in_order(api) -> None:
    listed = (await api.get("/catalogue")).json()

    assert [category["name"] for category in listed] == [
        "Finanzas",
        "IA",
        "Alimentación",
        "Salud",
        "Lugares",
        "Libros",
        "Calendario",
        "Notas",
        "Economía",
        "Ocio",
        "Tiempo",
    ]
    assert [p["id"] for p in listed[0]["providers"]] == [
        "enable_banking",
        "bitvavo",
        "imap",
        "frankfurter",
        "prices",
    ]


async def test_a_category_with_no_provider_yet_is_not_listed(api, monkeypatch) -> None:
    assert "places" in [category["id"] for category in (await api.get("/catalogue")).json()]

    monkeypatch.setattr(
        catalogue,
        "PROVIDERS",
        tuple(provider for provider in catalogue.PROVIDERS if provider.category != "places"),
    )
    listed = (await api.get("/catalogue")).json()

    assert "places" not in [category["id"] for category in listed]


async def test_every_source_is_configured_here_now(api) -> None:
    providers = {
        p["id"]: p
        for category in (await api.get("/catalogue")).json()
        for p in category["providers"]
    }

    assert all(p["lives_in"] is None for p in providers.values())
    assert all(p["available"] for p in providers.values())


async def test_bitvavo_is_connected_here_now_and_says_what_it_asks_for(api) -> None:
    providers = {
        p["id"]: p
        for category in (await api.get("/catalogue")).json()
        for p in category["providers"]
    }

    assert providers["bitvavo"]["available"] is True
    assert providers["bitvavo"]["lives_in"] is None
    assert providers["bitvavo"]["single"] is True
    assert [s["key"] for s in providers["bitvavo"]["secrets"]] == ["api_key", "api_secret"]


async def test_claude_accounts_are_added_here_each_with_its_own_name(api) -> None:
    providers = {
        p["id"]: p
        for category in (await api.get("/catalogue")).json()
        for p in category["providers"]
    }
    first = await api.post(
        "/connections",
        json={"provider": "claude", "label": "Personal", "secrets": {"token": "sintetico-abc"}},
    )
    twin = await api.post(
        "/connections",
        json={"provider": "claude", "label": " personal ", "secrets": {"token": "sintetico-def"}},
    )
    work = await api.post(
        "/connections",
        json={"provider": "claude", "label": "Trabajo", "secrets": {"token": "sintetico-ghi"}},
    )

    assert providers["claude"]["available"] is True
    assert (providers["claude"]["lives_in"], providers["claude"]["created_in"]) == (None, None)
    assert [s["key"] for s in providers["claude"]["secrets"]] == ["token"]
    assert first.status_code == 201
    assert twin.status_code == 409
    assert "Personal" in twin.json()["detail"]
    assert work.status_code == 201


async def test_a_connection_is_renamed_but_not_onto_another_claude_account(api) -> None:
    token = {"token": "sintetico-abc"}
    personal = (
        await api.post(
            "/connections", json={"provider": "claude", "label": "Personal", "secrets": token}
        )
    ).json()
    await api.post(
        "/connections", json={"provider": "claude", "label": "Trabajo", "secrets": token}
    )

    renamed = await api.put(f"/connections/{personal['id']}/label", json={"label": "  Casa  "})
    clash = await api.put(f"/connections/{personal['id']}/label", json={"label": "trabajo"})
    same = await api.put(f"/connections/{personal['id']}/label", json={"label": "CASA"})
    missing = await api.put(f"/connections/{uuid4()}/label", json={"label": "Otra"})

    assert (renamed.status_code, renamed.json()["label"]) == (200, "Casa")
    assert clash.status_code == 409
    assert (same.status_code, same.json()["label"]) == (200, "CASA")
    assert missing.status_code == 404


async def test_claude_is_never_synced_by_hand(api) -> None:
    created = (
        await api.post("/connections", json={"provider": "claude", "secrets": {"token": "sint"}})
    ).json()

    answer = await api.post(f"/connections/{created['id']}/sync")

    assert answer.status_code == 409
    assert "a mano" in answer.json()["detail"]


def test_every_category_the_hub_brings_is_one_a_module_can_consume() -> None:
    from kernel.manifests import CATEGORIES

    assert {category.id for category in catalogue.CATEGORIES} == set(CATEGORIES)
    for provider in catalogue.PROVIDERS:
        assert provider.category in CATEGORIES
        for event_type in provider.emits:
            assert event_type.split(".", 1)[0] == provider.category, event_type


async def test_with_nothing_connected_the_list_is_empty(api) -> None:
    response = await api.get("/connections")

    assert response.status_code == 200
    assert response.json() == []


async def test_with_nothing_connected_the_widget_is_empty_and_says_why(api) -> None:
    body = (await api.get("/widgets/status")).json()

    assert body["state"] == "empty"
    assert body["body"]["detail"] == "nada conectado todavía"
    validate("list", body["body"], body["state"])


async def test_a_widget_it_does_not_have_is_a_404(api) -> None:
    assert (await api.get("/widgets/otro")).status_code == 404


async def test_without_the_master_key_it_does_not_start(monkeypatch) -> None:
    from arga_crypto import NotConfigured
    from hub import credentials

    monkeypatch.delenv("HUB_CREDENTIALS_KEY")
    credentials.masters.cache_clear()
    try:
        with pytest.raises(NotConfigured, match="HUB_CREDENTIALS_KEY"):
            async with app.router.lifespan_context(app):
                pass
    finally:
        monkeypatch.undo()
        credentials.masters.cache_clear()
