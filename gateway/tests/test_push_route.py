import time

import httpx
import pytest
from conftest import install_login, login_environment
from test_routing import seen, upstream

from gateway import main


@pytest.fixture
async def anonymous(monkeypatch: pytest.MonkeyPatch):
    seen.clear()
    login_environment(monkeypatch)
    main.app.state.client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream), timeout=5.0
    )
    install_login(main.app, main.app.state.client)
    main.app.state.modules = (time.monotonic(), {"hub", "vitals"})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://arga"
    ) as client:
        yield client
    main.app.state.modules = None
    await main.app.state.client.aclose()


async def test_a_push_reaches_hub_without_a_session(anonymous) -> None:
    response = await anonymous.post(
        "/api/hub/push/apple-health",
        json=[{"date": "2026-09-24", "steps": 9120}],
        headers={"authorization": "Bearer el-token"},
    )

    assert response.status_code == 200
    assert seen[-1]["path"] == "/push/apple-health"
    assert seen[-1]["headers"]["authorization"] == "Bearer el-token"


async def test_no_identity_travels_and_none_can_be_forged(anonymous) -> None:
    await anonymous.post(
        "/api/hub/push/apple-health",
        json=[],
        headers={"x-arga-user": "otra-persona", "x-arga-subject": "otro", "x-arga-scopes": "x"},
    )

    headers = seen[-1]["headers"]
    assert "x-arga-user" not in headers
    assert "x-arga-subject" not in headers
    assert "x-arga-scopes" not in headers


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/hub/push/apple-health"),
        ("POST", "/api/hub/connections"),
        ("GET", "/api/hub/connections"),
        ("POST", "/api/hub/pushy"),
        ("POST", "/api/vitals/push/apple-health"),
        ("POST", "/api/kernel/push/x"),
    ],
)
async def test_everything_else_still_needs_a_session(anonymous, method: str, path: str) -> None:
    response = await anonymous.request(method, path, json=[])

    assert response.status_code == 401
    assert seen == []


async def test_without_hub_installed_it_is_a_404(anonymous) -> None:
    main.app.state.modules = (time.monotonic(), set())

    response = await anonymous.post("/api/hub/push/apple-health", json=[])

    assert response.status_code == 404
    assert seen == []
