import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel import capabilities
from kernel.db import engine
from kernel.main import app

ASKS = "probe_asks"
SILENT = "probe_silent"

REGISTER = text("""
    insert into kernel.modules (id, version, enabled, manifest)
    values (:id, '0.1.0', :enabled, cast(:manifest as jsonb))
    on conflict (id) do update set manifest = excluded.manifest, enabled = excluded.enabled
""")


@pytest.fixture
async def declared(database_url: str, monkeypatch):
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "probe-token")
    reached: list[httpx.Request] = []

    def hub(request: httpx.Request) -> httpx.Response:
        reached.append(request)
        return httpx.Response(200, json={"connection": "x", "created": True})

    monkeypatch.setattr(capabilities, "hub_transport", lambda: httpx.MockTransport(hub))
    async with engine().begin() as connection:
        for module, uses, enabled in (
            (ASKS, ["bitvavo.handoff"], True),
            (SILENT, [], True),
        ):
            await connection.execute(
                REGISTER,
                {"id": module, "enabled": enabled, "manifest": json.dumps({"uses": uses})},
            )
    yield reached
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.modules where id in (:a, :b)"), {"a": ASKS, "b": SILENT}
        )
    await engine().dispose()


async def ask(module: str, capability: str = "bitvavo.handoff") -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as kernel:
        return await kernel.post(
            f"/internal/capabilities/{capability}",
            json={"secrets": {}},
            headers={"x-arga-module": module},
        )


async def test_what_the_manifest_declares_goes_to_the_hub_with_who_asks(declared) -> None:
    response = await ask(ASKS)

    assert response.status_code == 200
    [request] = declared
    assert request.url.path == "/capabilities/bitvavo.handoff"
    assert request.headers["x-module-token"] == "probe-token"
    assert request.headers["x-arga-module"] == ASKS
    assert request.headers["x-arga-user"]


async def test_what_it_does_not_declare_never_reaches_the_hub(declared) -> None:
    response = await ask(SILENT)

    assert response.status_code == 403
    assert "uses" in response.json()["detail"]
    assert declared == []


async def test_a_module_that_is_not_registered_asks_nothing(declared) -> None:
    assert (await ask("probe_nobody")).status_code == 403
    assert declared == []


async def test_the_gateway_does_not_route_it_from_outside() -> None:
    assert capabilities.router.routes[0].path.startswith("/internal/")


SERVES = "probe_serves"


@pytest.fixture
async def served(declared, monkeypatch):
    reached: list[httpx.Request] = []

    def module(request: httpx.Request) -> httpx.Response:
        reached.append(request)
        return httpx.Response(200, json={"added": []})

    monkeypatch.setattr(capabilities, "module_transport", lambda: httpx.MockTransport(module))
    monkeypatch.setenv("MODULE_URL_TEMPLATE", "http://{module}.test:8000")
    async with engine().begin() as connection:
        await connection.execute(
            REGISTER,
            {
                "id": ASKS,
                "enabled": True,
                "manifest": json.dumps({"uses": ["bitvavo.handoff", "shopping.add"]}),
            },
        )
        await connection.execute(
            REGISTER,
            {"id": SERVES, "enabled": True, "manifest": json.dumps({"provides": ["shopping.add"]})},
        )
    yield reached
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :id"), {"id": SERVES})


async def test_what_an_app_serves_goes_to_that_app_and_not_to_the_hub(declared, served) -> None:
    response = await ask(ASKS, "shopping.add")

    assert response.status_code == 200
    assert declared == []
    [request] = served
    assert request.url.host == f"{SERVES}.test"
    assert request.url.path == "/capabilities/shopping.add"
    assert request.headers["x-module-token"] == "probe-token"
    assert request.headers["x-arga-module"] == ASKS
    assert request.headers["x-arga-user"]


async def test_serving_it_does_not_let_anyone_ask(declared, served) -> None:
    assert (await ask(SILENT, "shopping.add")).status_code == 403
    assert served == []


async def test_what_no_app_serves_still_goes_to_the_hub(declared, served) -> None:
    assert (await ask(ASKS)).status_code == 200
    assert served == []
    assert len(declared) == 1


async def test_an_app_that_is_switched_off_serves_nothing(declared, served) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("update kernel.modules set enabled = false where id = :id"), {"id": SERVES}
        )

    await ask(ASKS, "shopping.add")

    assert served == []


async def test_when_the_app_is_down_the_answer_says_which(declared, served, monkeypatch) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no está")

    monkeypatch.setattr(capabilities, "module_transport", lambda: httpx.MockTransport(down))

    response = await ask(ASKS, "shopping.add")

    assert response.status_code == 503
    assert SERVES in response.json()["detail"]


MOVES_A = "probe_moves_a"
MOVES_B = "probe_moves_b"
MOVE = "agenda.move"


@pytest.fixture
async def owners(declared, monkeypatch):
    reached: list[httpx.Request] = []

    def module(request: httpx.Request) -> httpx.Response:
        reached.append(request)
        return httpx.Response(200, json={"agenda": {}})

    monkeypatch.setattr(capabilities, "module_transport", lambda: httpx.MockTransport(module))
    monkeypatch.setenv("MODULE_URL_TEMPLATE", "http://{module}.test:8000")
    async with engine().begin() as connection:
        await connection.execute(
            REGISTER,
            {"id": ASKS, "enabled": True, "manifest": json.dumps({"uses": [MOVE]})},
        )
        for owner in (MOVES_A, MOVES_B):
            await connection.execute(
                REGISTER,
                {"id": owner, "enabled": True, "manifest": json.dumps({"provides": [MOVE]})},
            )
    yield reached
    async with engine().begin() as connection:
        await connection.execute(
            text("delete from kernel.modules where id in (:a, :b)"), {"a": MOVES_A, "b": MOVES_B}
        )


async def ask_to(module: str, target: str | None) -> httpx.Response:
    headers = {"x-arga-module": module}
    if target:
        headers["x-arga-target"] = target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://kernel") as kernel:
        return await kernel.post(f"/internal/capabilities/{MOVE}", json={}, headers=headers)


async def test_it_goes_to_the_app_it_names_among_several(declared, owners) -> None:
    assert (await ask_to(ASKS, MOVES_B)).status_code == 200
    [request] = owners
    assert request.url.host == f"{MOVES_B}.test"
    assert request.url.path == f"/capabilities/{MOVE}"
    assert declared == []


async def test_without_naming_one_it_goes_nowhere(declared, owners) -> None:
    assert (await ask_to(ASKS, None)).status_code == 422
    assert owners == [] and declared == []


async def test_an_app_that_does_not_serve_it_is_not_asked_nor_the_hub(declared, owners) -> None:
    response = await ask_to(ASKS, SILENT)
    assert response.status_code == 404
    assert owners == [] and declared == []


async def test_naming_the_app_does_not_skip_uses(declared, owners) -> None:
    assert (await ask_to(SILENT, MOVES_A)).status_code == 403
    assert owners == []
