import time

import httpx
import jwt
import pytest
from conftest import (
    KID,
    USER,
    install_login,
    jwks,
    login_environment,
    session_cookie,
    signing_key,
    token,
)
from fastapi import FastAPI, Request

from gateway import main
from gateway import oauth as oauth_module
from gateway.session import COOKIE

upstream = FastAPI()
seen: list[dict] = []


@upstream.get("/cdn-cgi/access/certs")
async def certs() -> dict:
    return jwks()


@upstream.get("/tools")
async def tools() -> list[dict]:
    return [
        {"module": "training", "name": "get_sessions", "scope": "training:read"},
        {"module": "training", "name": "log_bodyweight", "scope": "training:write"},
    ]


@upstream.get("/modules")
async def modules() -> list[dict]:
    return [{"id": "training", "enabled": True}]


@upstream.get("/auth/realms/arga/protocol/openid-connect/certs")
async def oauth_certs() -> dict:
    return jwks()


@upstream.post("/internal/users")
async def people() -> dict:
    return {"id": USER}


@upstream.api_route("/{path:path}", methods=["GET", "POST"])
async def catch_all(request: Request, path: str) -> dict:
    seen.append({**dict(request.headers), "_host": request.url.hostname, "path": request.url.path})
    return {"saw": request.url.path}


ISSUER = "https://arga.test/auth/realms/arga"
RESOURCE = "https://arga.test/mcp"


def oauth_token(scopes: str = "training:read", **overrides) -> str:
    claims = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "owner-id",
        "scope": scopes,
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
async def anonymous(monkeypatch: pytest.MonkeyPatch):
    seen.clear()
    login_environment(monkeypatch)
    monkeypatch.setenv("OAUTH_ISSUER", ISSUER)
    monkeypatch.setenv("MCP_RESOURCE_URL", RESOURCE)
    monkeypatch.setenv(
        "OAUTH_JWKS_URL", "http://auth:8080/auth/realms/arga/protocol/openid-connect/certs"
    )
    main.app.state.client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream), timeout=5.0
    )
    main.app.state.oauth = oauth_module.from_environment(main.app.state.client)
    install_login(main.app, main.app.state.client)
    main.app.state.remote_scopes = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://arga"
    ) as client:
        yield client
    await main.app.state.client.aclose()


async def test_mcp_with_a_valid_token_carries_its_subject_and_scopes_inside(anonymous) -> None:
    response = await anonymous.post(
        "/mcp",
        json={"jsonrpc": "2.0"},
        headers={
            "authorization": f"Bearer {oauth_token('training:read')}",
            "x-arga-subject": "suplantado",
            "x-arga-scopes": "training:write",
        },
    )

    assert response.status_code == 200
    (request,) = seen
    assert (request["_host"], request["path"]) == ("mcp", "/mcp")
    assert request["x-arga-subject"] == "owner-id"
    assert request["x-arga-scopes"] == "training:read"
    assert request["x-arga-user"] == USER


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "https://otra.cosa/api"}, {"iss": "https://otro.emisor"}, {"exp": 1}],
    ids=["otra-audiencia", "otro-emisor", "caducado"],
)
async def test_a_token_that_is_not_for_mcp_does_not_get_through(anonymous, overrides) -> None:
    response = await anonymous.post(
        "/mcp", json={}, headers={"authorization": f"Bearer {oauth_token(**overrides)}"}
    )

    assert response.status_code == 401
    assert not seen


async def test_without_a_token_it_says_where_to_get_one(anonymous) -> None:
    unauthorised = await anonymous.post("/mcp", json={})
    metadata = await anonymous.get("/.well-known/oauth-protected-resource/mcp")

    assert unauthorised.status_code == 401
    assert unauthorised.headers["www-authenticate"] == (
        'Bearer error="invalid_token", '
        'resource_metadata="https://arga.test/.well-known/oauth-protected-resource/mcp", '
        'scope="training:read"'
    )
    assert metadata.json() == {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["training:read"],
    }
    assert not seen


async def test_the_remote_connector_is_never_told_to_ask_for_write(anonymous) -> None:
    challenge = (await anonymous.post("/mcp", json={})).headers["www-authenticate"]
    metadata = (await anonymous.get("/.well-known/oauth-protected-resource/mcp")).json()

    assert ":write" not in challenge
    assert not [scope for scope in metadata["scopes_supported"] if scope.endswith(":write")]


async def test_without_an_authorization_server_mcp_is_closed_not_open(anonymous) -> None:
    main.app.state.oauth = None

    response = await anonymous.post("/mcp", json={}, headers={"x-arga-scopes": "training:write"})

    assert response.status_code == 503
    assert not seen


@pytest.mark.parametrize("kind", ["oauth-authorization-server", "openid-configuration"])
async def test_rfc8414_metadata_is_rewritten_to_where_keycloak_serves_it(anonymous, kind) -> None:
    response = await anonymous.get(f"/.well-known/{kind}/auth/realms/arga")

    assert response.status_code == 200
    assert (seen[0]["_host"], seen[0]["path"]) == ("auth", f"/auth/realms/arga/.well-known/{kind}")


async def test_the_login_and_token_endpoints_of_the_arga_realm_are_public(anonymous) -> None:
    for path in (
        "/auth/realms/arga/protocol/openid-connect/auth",
        "/auth/realms/arga/protocol/openid-connect/token",
        "/auth/resources/abc/login/keycloak.v2/css/styles.css",
    ):
        assert (await anonymous.get(path)).status_code == 200, path


@pytest.mark.parametrize(
    "path",
    [
        "/auth/admin/master/console/",
        "/auth/admin/realms/arga/users",
        "/auth/realms/master/protocol/openid-connect/auth",
        "/auth/realms/arga-falso/protocol/openid-connect/auth",
        "/auth/",
        "/.well-known/openid-configuration/auth/realms/master",
    ],
)
async def test_the_console_and_the_master_realm_are_not_published(anonymous, path) -> None:
    headers = {
        "cookie": f"{COOKIE}={session_cookie()}",
        "cf-access-jwt-assertion": token(audience="aud-de-prueba"),
    }
    response = await anonymous.get(path, headers=headers)

    assert response.status_code == 404
    assert not seen


@pytest.mark.parametrize(
    "path",
    [
        "/apple-touch-icon.png",
        "/icon-192.png",
        "/icon-512.png",
        "/icon.svg",
        "/manifest.webmanifest",
    ],
)
async def test_the_install_assets_arrive_without_a_session(anonymous, path) -> None:
    response = await anonymous.get(path)

    assert response.status_code == 200
    assert (seen[0]["_host"], seen[0]["path"]) == ("shell", path)
    assert "x-arga-subject" not in seen[0]


async def test_the_rest_of_the_shell_still_needs_a_session(anonymous) -> None:
    for path in ("/", "/icon-192.png.bak", "/wallpapers/marea.svg"):
        assert (await anonymous.get(path)).status_code == 401, path
    assert (await anonymous.post("/manifest.webmanifest")).status_code == 401


async def test_a_module_app_is_served_from_its_own_service_with_a_session(anonymous) -> None:
    main.app.state.modules = None
    without = await anonymous.get("/training/")
    with_session = await anonymous.get(
        "/training/sesion/42", headers={"cookie": f"{COOKIE}={session_cookie()}"}
    )

    assert without.status_code == 401
    assert with_session.status_code == 200
    (request,) = seen
    assert (request["_host"], request["path"]) == ("training", "/training/sesion/42")
    assert "x-arga-subject" in request


async def test_a_module_app_installs_with_its_icon_without_a_session(anonymous) -> None:
    main.app.state.modules = None
    for path in ("/training/apple-touch-icon.png", "/training/manifest.webmanifest"):
        assert (await anonymous.get(path)).status_code == 200, path
    assert [r["path"] for r in seen] == [
        "/training/apple-touch-icon.png",
        "/training/manifest.webmanifest",
    ]
    assert all("x-arga-subject" not in r for r in seen)


async def test_a_path_that_is_not_an_installed_module_is_still_the_shell(anonymous) -> None:
    main.app.state.modules = None
    response = await anonymous.get(
        "/wallpapers/marea.svg", headers={"cookie": f"{COOKIE}={session_cookie()}"}
    )

    assert response.status_code == 200
    assert [r["_host"] for r in seen] == ["shell"]
