import gzip

import httpx
import pytest
from conftest import USER, install_login, login_environment, session_cookie
from fastapi import FastAPI, Request, Response

from gateway import main
from gateway.session import COOKIE

upstream = FastAPI()
seen: list[dict] = []

COMPRESSED = gzip.compress(b"<h1>Hoy</h1>")
SPACE = "0c0c0c0c-0000-4000-8000-00000000c0c0"


@upstream.get("/compressed")
async def compressed() -> Response:
    return Response(
        content=COMPRESSED, media_type="text/html", headers={"content-encoding": "gzip"}
    )


@upstream.get("/timed")
async def timed() -> Response:
    return Response(
        content=b"{}",
        media_type="application/json",
        headers={"server-timing": 'db;dur=1.5;desc="2 consultas", app;dur=4.0'},
    )


@upstream.post("/internal/users")
async def people() -> dict:
    return {
        "id": USER,
        "spaces": [SPACE],
        "preferences": {
            "locale": "es",
            "timezone": "America/Argentina/Buenos_Aires",
            "currency": "ARS",
            "country": "AR",
            "region": None,
            "area": "bad value\r\nx-evil: 1",
        },
    }


@upstream.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
)
async def catch_all(request: Request, path: str) -> dict:
    body = await request.body()
    seen.append(
        {
            "path": request.url.path,
            "query": str(request.url.query),
            "method": request.method,
            "body": body.decode(),
            "headers": dict(request.headers),
        }
    )
    return {"saw": request.url.path}


@pytest.fixture
async def api(monkeypatch: pytest.MonkeyPatch):
    seen.clear()
    login_environment(monkeypatch)
    main.app.state.client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream), timeout=5.0
    )
    install_login(main.app, main.app.state.client)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://arga",
        cookies={COOKIE: session_cookie()},
    ) as client:
        yield client
    await main.app.state.client.aclose()


async def test_the_kernel_never_sees_the_prefix(api) -> None:
    response = await api.get("/api/kernel/readyz")

    assert response.status_code == 200
    assert seen[-1]["path"] == "/readyz"


async def test_the_query_string_survives(api) -> None:
    await api.get("/api/kernel/events?module=finance&limit=5")

    assert seen[-1]["path"] == "/events"
    assert seen[-1]["query"] == "module=finance&limit=5"


async def test_a_body_survives(api) -> None:
    await api.post("/api/kernel/events", json={"module": "finance"})

    assert seen[-1]["method"] == "POST"
    assert seen[-1]["body"] == '{"module":"finance"}'


async def test_everything_else_goes_to_the_shell(api) -> None:
    await api.get("/dashboard")

    assert seen[-1]["path"] == "/dashboard"


async def test_the_root_goes_to_the_shell(api) -> None:
    await api.get("/")

    assert seen[-1]["path"] == "/"


async def test_an_unknown_module_says_so(api) -> None:
    response = await api.get("/api/finance/transactions")

    assert response.status_code == 404
    assert response.json()["detail"] == "module 'finance' is not installed"
    assert [r["path"] for r in seen if r["path"] != "/modules"] == []


async def test_healthz_is_the_gateways_own(api) -> None:
    response = await api.get("/healthz")

    assert response.json() == {"status": "ok"}
    assert seen == []


async def test_version_is_the_gateways_own(api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v0.9.0")

    response = await api.get("/version")

    assert response.json() == {"service": "gateway", "version": "v0.9.0"}
    assert seen == []


async def test_the_clients_connection_semantics_are_not_propagated(api) -> None:
    await api.post("/api/kernel/events", json={"a": 1}, headers={"connection": "close"})

    assert seen[-1]["headers"].get("connection") != "close"


async def test_the_body_is_streamed_through(api) -> None:
    await api.post("/api/kernel/events", json={"a": 1})

    assert seen[-1]["body"] == '{"a":1}'
    assert "content-length" not in seen[-1]["headers"]
    assert seen[-1]["headers"].get("transfer-encoding") == "chunked"


async def test_a_compressed_body_arrives_readable(api) -> None:
    response = await api.get("/compressed")

    assert response.headers["content-encoding"] == "gzip"
    assert response.text == "<h1>Hoy</h1>"


async def test_an_upstream_that_is_down_is_a_502_not_a_crash(api) -> None:
    main.app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(1.0, connect=0.2))
    try:
        response = await api.get("/api/kernel/readyz")
    finally:
        await main.app.state.client.aclose()

    assert response.status_code == 502
    assert "not answering" in response.json()["detail"]


async def test_a_module_that_the_kernel_does_not_know_is_a_404(api) -> None:
    main.app.state.modules = (0.0, set())
    response = await api.get("/api/inventado/widgets/main")

    assert response.status_code == 404
    assert "inventado" in response.json()["detail"]


@pytest.mark.parametrize("module_id", ["Demo", "demo-1", "kernel-internal", "a", "demo%20"])
async def test_an_id_that_is_not_an_id_never_reaches_a_hostname(api, module_id: str) -> None:
    response = await api.get(f"/api/{module_id}/x")

    assert response.status_code == 404


async def test_the_person_travels_with_the_subject_and_cannot_be_forged(api) -> None:
    await api.get("/api/kernel/ui/layouts", headers={"x-arga-user": "otra-persona"})

    assert seen[-1]["headers"]["x-arga-user"] == USER


async def test_the_spaces_travel_with_the_person_and_cannot_be_forged(api) -> None:
    forged = "0f0f0f0f-0000-4000-8000-00000000f0f0"
    await api.get("/api/kernel/ui/layouts", headers={"x-arga-spaces": forged})

    assert seen[-1]["headers"]["x-arga-spaces"] == SPACE


async def test_the_preferences_travel_with_the_person_and_cannot_be_forged(api) -> None:
    await api.get(
        "/api/kernel/ui/layouts", headers={"x-arga-locale": "en", "x-arga-region": "ES-NA"}
    )

    sent = seen[-1]["headers"]
    assert sent["x-arga-locale"] == "es"
    assert sent["x-arga-timezone"] == "America/Argentina/Buenos_Aires"
    assert sent["x-arga-currency"] == "ARS"
    assert sent["x-arga-country"] == "AR"
    assert "x-arga-region" not in sent
    assert "x-arga-area" not in sent
    assert "x-evil" not in sent


async def test_the_person_is_asked_once_and_not_on_every_request(api) -> None:
    asked = []
    original = main.app.state.people.client.post

    async def counted(url, *args, **kwargs):
        if str(url).endswith("/internal/users"):
            asked.append(url)
        return await original(url, *args, **kwargs)

    main.app.state.people.client.post = counted
    main.app.state.people._known.clear()
    for _ in range(3):
        await api.get("/api/kernel/ui/layouts")

    assert len(asked) == 1


@pytest.mark.parametrize(
    ("method", "path", "asks_again"),
    [
        ("POST", "/api/kernel/spaces/join", True),
        ("DELETE", f"/api/kernel/spaces/{SPACE}/members/{USER}", True),
        ("GET", "/api/kernel/spaces", False),
        ("PUT", "/api/kernel/ui/preferences", False),
        ("PATCH", "/api/kernel/me/preferences", True),
        ("GET", "/api/kernel/me/preferences", False),
    ],
)
async def test_whoever_changes_their_spaces_sees_them_at_once(
    api, method: str, path: str, asks_again: bool
) -> None:
    asked = []
    original = main.app.state.people.client.post

    async def counted(url, *args, **kwargs):
        if str(url).endswith("/internal/users"):
            asked.append(url)
        return await original(url, *args, **kwargs)

    main.app.state.people.client.post = counted
    main.app.state.people._known.clear()
    await api.get("/api/kernel/ui/layouts")
    await api.request(method, path)
    await api.get("/api/kernel/ui/layouts")

    assert len(asked) == (2 if asks_again else 1)


async def test_with_the_kernel_unable_to_say_who_it_is_the_request_still_goes_through(
    api,
) -> None:
    main.app.state.people._known.clear()
    main.app.state.people.kernel_url = "http://nadie:1"

    async def down(url, *args, **kwargs):
        raise httpx.ConnectError("el kernel no contesta")

    main.app.state.people.client = type("Down", (), {"post": staticmethod(down)})()
    response = await api.get("/api/kernel/ui/layouts")

    assert response.status_code == 200
    assert "x-arga-user" not in seen[-1]["headers"]


async def test_an_app_at_another_address_reaches_its_module(api) -> None:
    import time

    main.app.state.modules = (time.monotonic(), {"goals"}, {"kpis": "goals"})
    try:
        for path in ("/kpis/meta/1", "/goals/tarea/1"):
            response = await api.get(path)
            assert response.status_code == 200
            assert seen[-1]["path"] == path
            assert seen[-1]["headers"]["host"] == "goals:8000"
        await api.get("/otra")
        assert seen[-1]["headers"]["host"] != "goals:8000"
    finally:
        main.app.state.modules = None


async def test_the_gateway_adds_its_own_time_to_what_the_service_said(api) -> None:
    response = await api.get("/timed")

    service, gateway = response.headers["server-timing"].rsplit(", ", 1)
    assert service == 'db;dur=1.5;desc="2 consultas", app;dur=4.0'
    assert gateway.startswith("gw;dur=")


async def test_a_service_that_says_nothing_still_gets_the_gateway_time(api) -> None:
    response = await api.get("/api/kernel/readyz")

    assert response.headers["server-timing"].startswith("gw;dur=")
