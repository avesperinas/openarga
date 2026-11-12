from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from arga_module.publisher import listen_dsn
from arga_module.service import Service


class Missing(Exception):
    pass


class Clash(Exception):
    pass


def demo(tmp_path: Path) -> Service:
    (tmp_path / "index.html").write_text("<div id=root></div>")
    service = Service("demo", "Demo", errors={Missing: 404, Clash: 409}, ui_dist=tmp_path)

    @service.app.get("/things/{name}")
    async def thing(name: str) -> dict:
        if name == "nada":
            raise Missing(name)
        if name == "doble":
            raise Clash("ya hay una")
        return {"name": name}

    service.serve_ui()
    return service


@pytest.fixture
async def client(tmp_path: Path):
    service = demo(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=service.app), base_url="http://demo") as c:
        yield c


async def test_it_lives_and_says_its_version(client) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok", "module": "demo"}
    assert (await client.get("/version")).json()["service"] == "demo"


async def test_the_errors_of_the_domain_are_404_and_409_with_their_reason(client) -> None:
    missing = await client.get("/things/nada")
    clash = await client.get("/things/doble")

    assert (missing.status_code, missing.json()["detail"]) == (404, "no existe: nada")
    assert (clash.status_code, clash.json()["detail"]) == (409, "ya hay una")
    assert (await client.get("/things/una")).json() == {"name": "una"}


async def test_the_routes_of_the_module_come_before_the_app(client) -> None:
    assert (await client.get("/demo/una/pantalla")).text == "<div id=root></div>"
    assert (await client.get("/things/x")).json() == {"name": "x"}


async def test_a_missing_file_of_the_app_is_404_and_not_the_page(client) -> None:
    assert (await client.get("/demo/libro/1")).status_code == 200
    assert (await client.get("/demo/assets/index-viejo.js")).status_code == 404
    assert (await client.get("/demo/icono.svg")).status_code == 404


async def test_it_says_who_is_looking(client) -> None:
    person = "00000000-0000-4000-8000-000000000001"
    assert (await client.get("/me", headers={"x-arga-user": person})).json() == {"user_id": person}
    assert (await client.get("/me")).status_code == 422


async def test_without_tools_or_widgets_they_are_404(client) -> None:
    assert (await client.get("/widgets/main")).status_code == 404
    assert (await client.post("/tools/x", json={})).status_code == 404


def test_an_app_that_is_served_says_where_it_is_built() -> None:
    with pytest.raises(ValueError, match="construida"):
        Service("demo", "Demo")
    assert Service("demo", "Demo", ui=False).ui is False


def test_the_listener_speaks_plain_asyncpg() -> None:
    assert listen_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


class Nothing(BaseModel):
    pass


@dataclass(frozen=True)
class WaitingTool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict]]
    own_transactions: bool = True


async def test_a_tool_that_waits_on_another_service_opens_its_own_transactions(
    tmp_path: Path,
) -> None:
    received = []

    async def run(transaction, arguments: Nothing) -> dict:
        received.append(transaction)
        return {"callable": callable(transaction)}

    (tmp_path / "index.html").write_text("<div id=root></div>")
    service = Service(
        "demo",
        "Demo",
        tools={"ask": WaitingTool(Nothing, run)},
        role_for_scopes=lambda scopes: "mod_demo" if "demo:read" in scopes else None,
        ui_dist=tmp_path,
    )
    async with AsyncClient(transport=ASGITransport(app=service.app), base_url="http://demo") as c:
        answer = await c.post("/tools/ask", json={}, headers={"x-arga-scopes": "demo:read"})

    assert answer.json() == {"content": {"callable": True}}
    assert len(received) == 1
