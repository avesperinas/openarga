from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from conftest import (
    CLIENT_ID,
    CLIENT_SECRET,
    PUBLIC_URL,
    REALM_ISSUER,
    SUB,
    USER,
    install_login,
    login_environment,
    other_key,
    session_cookie,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from gateway import main
from gateway import session as session_module
from gateway.session import COOKIE, LOGIN_COOKIE

CORREO = "yo@ejemplo.com"
REALM_KID = "realm-key-1"
realm_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Realm:
    def __init__(self) -> None:
        self.codes: dict[str, dict] = {}
        self.refresh: str = "ok"
        self.refreshes = 0
        self.revoked: list[str] = []
        self.seen: list[dict] = []
        self.id_token_overrides: dict = {}

    def authorize(self, location: str, **identity) -> str:
        query = parse_qs(urlparse(location).query)
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "challenge": query["code_challenge"][0],
            "nonce": query["nonce"][0],
            "redirect_uri": query["redirect_uri"][0],
            "sub": SUB,
            "email": CORREO,
            "email_verified": True,
            **identity,
        }
        return f"/login/callback?code={code}&state={query['state'][0]}"

    def id_token(self, grant: dict) -> str:
        claims = {
            "iss": REALM_ISSUER,
            "aud": CLIENT_ID,
            "sub": grant["sub"],
            "nonce": grant["nonce"],
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
            "email": grant["email"],
            "email_verified": grant["email_verified"],
            **self.id_token_overrides,
        }
        key = self.id_token_overrides.pop("_key", realm_key)
        claims.pop("_key", None)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": REALM_KID})


realm = Realm()
upstream = FastAPI()


def client_authenticated(request: Request) -> bool:
    expected = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    return request.headers.get("authorization") == f"Basic {expected}"


def tokens(refresh_token: str, id_token: str | None = None) -> dict:
    body = {
        "access_token": "no-lo-mira-nadie",
        "expires_in": 900,
        "refresh_token": refresh_token,
        "refresh_expires_in": 14 * 86400,
        "token_type": "Bearer",
    }
    if id_token:
        body["id_token"] = id_token
    return body


@upstream.post("/auth/realms/arga/protocol/openid-connect/token")
async def token_endpoint(request: Request) -> Response:
    if not client_authenticated(request):
        return JSONResponse({"error": "unauthorized_client"}, status_code=401)
    form = await request.form()
    if form["grant_type"] == "authorization_code":
        grant = realm.codes.pop(str(form["code"]), None)
        if grant is None or form["redirect_uri"] != grant["redirect_uri"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        verifier = str(form["code_verifier"])
        digest = hashlib.sha256(verifier.encode()).digest()
        if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != grant["challenge"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        return JSONResponse(tokens("refresco-1", realm.id_token(grant)))
    if form["grant_type"] == "refresh_token":
        realm.refreshes += 1
        await asyncio.sleep(0.05)
        if realm.refresh == "rejected":
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if realm.refresh == "down":
            return JSONResponse({"error": "temporarily_unavailable"}, status_code=503)
        return JSONResponse(tokens(f"refresco-{realm.refreshes + 1}"))
    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)


@upstream.get("/auth/realms/arga/protocol/openid-connect/certs")
async def realm_certs() -> dict:
    public = jwt.algorithms.RSAAlgorithm.to_jwk(realm_key.public_key(), as_dict=True)
    return {"keys": [{**public, "kid": REALM_KID, "alg": "RS256", "use": "sig"}]}


@upstream.post("/auth/realms/arga/protocol/openid-connect/logout")
async def realm_logout(request: Request) -> Response:
    if client_authenticated(request):
        realm.revoked.append(str((await request.form())["refresh_token"]))
    return Response(status_code=204)


@upstream.get("/modules")
async def modules() -> list[dict]:
    return [{"id": "training", "enabled": True}, {"id": "library", "enabled": True}]


@upstream.post("/internal/users")
async def people() -> dict:
    return {"id": USER}


@upstream.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
async def catch_all(request: Request, path: str) -> dict:
    realm.seen.append({"path": request.url.path, "headers": dict(request.headers)})
    return {"saw": request.url.path}


@pytest.fixture
async def browser(monkeypatch: pytest.MonkeyPatch):
    global realm
    realm = Realm()
    login_environment(monkeypatch)
    main.app.state.client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream), timeout=5.0
    )
    main.app.state.oauth = None
    main.app.state.modules = None
    install_login(main.app, main.app.state.client)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url=PUBLIC_URL
    ) as client:
        yield client
    await main.app.state.client.aclose()


NAVIGATION = {"sec-fetch-mode": "navigate", "accept": "text/html"}


async def log_in(browser: httpx.AsyncClient, next_path: str = "/", **identity) -> httpx.Response:
    start = await browser.get("/login", params={"next": next_path})
    return await browser.get(realm.authorize(start.headers["location"], **identity))


def cookie_value(response: httpx.Response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


async def test_a_page_without_a_session_goes_to_the_login_and_comes_back(browser) -> None:
    response = await browser.get("/training/hoy?semana=3", headers=NAVIGATION)

    assert response.status_code == 302
    assert response.headers["location"] == "/login?next=%2Ftraining%2Fhoy%3Fsemana%3D3"
    assert realm.seen == []


@pytest.mark.parametrize(
    "headers",
    [
        {"accept": "application/json"},
        {"sec-fetch-mode": "cors", "accept": "*/*"},
        {"sec-fetch-mode": "cors", "accept": "text/html"},
    ],
)
async def test_an_api_call_without_a_session_is_a_401_and_not_html(browser, headers) -> None:
    response = await browser.get("/api/kernel/ui/layouts", headers=headers)

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/json"
    assert response.json()["login"] == "/login"
    assert realm.seen == []


async def test_a_write_without_a_session_is_never_redirected(browser) -> None:
    response = await browser.post("/api/training/sets", json={}, headers=NAVIGATION)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "path", ["/healthz", "/version", "/privacidad", "/manifest.webmanifest", "/sw.js"]
)
async def test_what_needed_no_login_still_needs_none(browser, path) -> None:
    assert (await browser.get(path)).status_code == 200


async def test_the_privacy_policy_says_what_is_read_and_what_is_never_done(browser) -> None:
    response = await browser.get("/privacidad", headers={"sec-fetch-mode": "navigate"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert "Limited Use" in page
    assert "read-only" in page and "solo permisos de" in page
    assert "never used to train" in page


async def test_login_asks_the_realm_for_a_code_with_pkce_and_goes_straight_to_google(
    browser,
) -> None:
    response = await browser.get("/login", params={"next": "/training/"})

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        f"{REALM_ISSUER}/protocol/openid-connect/auth"
    )
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [f"{PUBLIC_URL}/login/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["kc_idp_hint"] == ["google"]
    assert query["scope"] == ["openid"]
    assert cookie_value(response, LOGIN_COOKIE)
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


async def test_the_whole_login_leaves_a_session_that_reaches_the_kernel_as_the_sub(browser) -> None:
    done = await log_in(browser, "/training/hoy")

    assert done.status_code == 302
    assert done.headers["location"] == "/training/hoy"
    session = next(h for h in done.headers.get_list("set-cookie") if h.startswith(f"{COOKIE}="))
    for attribute in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/", "Max-Age="):
        assert attribute in session
    assert cookie_value(done, LOGIN_COOKIE) == ""

    response = await browser.get("/api/kernel/ui/layouts", headers={"x-arga-subject": "suplantado"})

    assert response.status_code == 200
    (seen,) = realm.seen
    assert seen["headers"]["x-arga-subject"] == SUB
    assert COOKIE not in seen["headers"].get("cookie", "")


async def test_other_cookies_still_reach_the_service_behind(browser) -> None:
    await log_in(browser)
    browser.cookies.set("preferencia", "compacta", domain="arga.test")

    await browser.get("/api/kernel/ui/layouts")

    assert realm.seen[-1]["headers"]["cookie"] == "preferencia=compacta"


@pytest.mark.parametrize(
    "next_path", ["https://otro.sitio/", "//otro.sitio/", "/\\otro.sitio", "javascript:alert(1)"]
)
async def test_the_return_address_is_always_here(browser, next_path) -> None:
    done = await log_in(browser, next_path)

    assert done.headers["location"] == "/"


async def test_a_callback_without_its_login_cookie_does_not_log_in(browser) -> None:
    start = await browser.get("/login")
    callback = realm.authorize(start.headers["location"])
    browser.cookies.clear()

    response = await browser.get(callback)

    assert response.status_code == 400
    assert cookie_value(response, COOKIE) is None


async def test_a_callback_for_another_login_does_not_log_in(browser) -> None:
    mine = await browser.get("/login")
    theirs = realm.authorize(mine.headers["location"]).replace("state=", "state=otro")

    response = await browser.get(theirs)

    assert response.status_code == 400
    assert cookie_value(response, COOKIE) is None


async def test_a_code_cannot_be_used_twice(browser) -> None:
    start = await browser.get("/login")
    callback = realm.authorize(start.headers["location"])
    await browser.get(callback)
    browser.cookies.clear()
    again = await browser.get("/login")
    state = parse_qs(urlparse(again.headers["location"]).query)["state"][0]
    code = parse_qs(urlparse(callback).query)["code"][0]

    response = await browser.get(f"/login/callback?code={code}&state={state}")

    assert response.status_code == 400
    assert cookie_value(response, COOKIE) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"nonce": "de-otra-peticion"},
        {"aud": "otro-cliente"},
        {"iss": "https://otro.emisor/realms/arga"},
        {"exp": 1},
        {"_key": other_key},
    ],
    ids=["nonce", "audiencia", "emisor", "caducado", "firma"],
)
async def test_an_identity_token_that_does_not_verify_does_not_log_in(browser, overrides) -> None:
    realm.id_token_overrides = dict(overrides)

    done = await log_in(browser)

    assert done.status_code == 400
    assert cookie_value(done, COOKIE) is None


async def test_a_tampered_cookie_is_no_session(browser) -> None:
    value = session_cookie()
    tampered = value[:-4] + ("AAAA" if not value.endswith("AAAA") else "BBBB")

    response = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={tampered}"})

    assert response.status_code == 401


async def test_a_cookie_sealed_with_another_secret_is_no_session(browser) -> None:
    forged = session_cookie(secret="otro-secreto-que-no-es-el-del-gateway-ni-de-lejos")

    response = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={forged}"})

    assert response.status_code == 401


async def test_the_login_cookie_does_not_open_as_a_session(browser) -> None:
    start = await browser.get("/login")
    login_value = cookie_value(start, LOGIN_COOKIE)
    browser.cookies.clear()

    response = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={login_value}"})

    assert response.status_code == 401


async def test_an_expired_session_is_refreshed_and_the_new_cookie_comes_back(browser) -> None:
    value = session_cookie(expires_in=-10)

    response = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={value}"})

    assert response.status_code == 200
    assert realm.refreshes == 1
    renewed = cookie_value(response, COOKIE)
    assert renewed and renewed != value
    assert main.app.state.sessions.read(renewed).refresh_token == "refresco-2"


async def test_a_disabled_person_is_out_at_the_next_refresh(browser) -> None:
    realm.refresh = "rejected"
    value = session_cookie(expires_in=-10)

    api = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={value}"})
    page = await browser.get("/", headers={**NAVIGATION, "cookie": f"{COOKIE}={value}"})

    assert api.status_code == 401
    assert page.status_code == 302
    assert page.headers["location"].startswith("/login")
    assert realm.seen == []


async def test_a_session_past_its_refresh_lifetime_is_over_without_asking(browser) -> None:
    value = session_cookie(expires_in=-10, refresh_expires_in=-5)

    response = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={value}"})

    assert response.status_code == 401
    assert realm.refreshes == 0


async def test_while_the_realm_is_down_a_recent_session_keeps_working(browser) -> None:
    realm.refresh = "down"
    value = session_cookie(expires_in=-10)

    response = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={value}"})

    assert response.status_code == 200
    assert cookie_value(response, COOKIE) is None


async def test_while_the_realm_is_down_an_old_session_is_a_503_not_a_logout(browser) -> None:
    realm.refresh = "down"
    value = session_cookie(expires_in=-(session_module.GRACE_SECONDS + 60))

    response = await browser.get("/api/kernel/x", headers={"cookie": f"{COOKIE}={value}"})

    assert response.status_code == 503
    assert realm.seen == []


async def test_ten_widgets_at_once_refresh_the_session_once(browser) -> None:
    value = session_cookie(expires_in=-10)

    responses = await asyncio.gather(
        *(
            browser.get(f"/api/kernel/w/{n}", headers={"cookie": f"{COOKIE}={value}"})
            for n in range(10)
        )
    )

    assert [r.status_code for r in responses] == [200] * 10
    assert realm.refreshes == 1


async def test_the_internal_kernel_api_is_not_reachable_with_a_session(browser) -> None:
    await log_in(browser)

    response = await browser.post("/api/kernel/internal/users", json={"subject": "otro-sub"})

    assert response.status_code == 404
    assert realm.seen == []


async def test_logout_closes_the_realm_session_and_clears_the_cookie(browser) -> None:
    await log_in(browser)

    response = await browser.post("/logout")

    assert response.status_code == 200
    assert realm.revoked == ["refresco-1"]
    assert cookie_value(response, COOKIE) == ""
    assert (await browser.get("/api/kernel/x")).status_code == 401


async def test_logout_forgets_what_this_device_kept(browser) -> None:
    await log_in(browser)

    response = await browser.post("/logout")
    again = await browser.get("/logout")

    for answer in (response, again):
        assert answer.headers["clear-site-data"] == '"cache", "storage"'
        assert "indexedDB.deleteDatabase" in answer.text
        assert "localStorage.clear()" in answer.text
        assert "serviceWorker.getRegistrations" in answer.text


async def test_login_with_a_live_session_just_goes_back(browser) -> None:
    await log_in(browser)

    response = await browser.get("/login", params={"next": "/library/"})

    assert response.status_code == 302
    assert response.headers["location"] == "/library/"


@pytest.mark.parametrize(
    "missing",
    [
        "OAUTH_ISSUER",
        "OIDC_INTERNAL_URL",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "PUBLIC_URL",
        "SESSION_SECRET",
    ],
)
def test_the_process_really_does_exit_without_login_configuration(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    login_environment(monkeypatch)
    environment = {**os.environ}
    environment.pop(missing)
    for access in ("ACCESS_TEAM_DOMAIN", "ACCESS_AUD"):
        environment.pop(access, None)

    finished = subprocess.run(
        [sys.executable, "-m", "uvicorn", "gateway.main:app", "--port", "8124"],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
    )

    assert finished.returncode != 0
    assert missing in finished.stderr + finished.stdout


def test_a_short_session_secret_is_refused() -> None:
    with pytest.raises(session_module.NotConfigured):
        session_module.Sealer("corto")


def test_the_gateway_starts_without_cloudflare_access(monkeypatch: pytest.MonkeyPatch) -> None:
    login_environment(monkeypatch)
    environment = {**os.environ}
    for access in ("ACCESS_TEAM_DOMAIN", "ACCESS_AUD"):
        environment.pop(access, None)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "gateway.main:app", "--port", "8125"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
    )
    try:
        for _ in range(100):
            try:
                if httpx.get("http://127.0.0.1:8125/healthz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            pytest.fail("el gateway no llegó a contestar /healthz sin Access")
        assert server.poll() is None
    finally:
        server.terminate()
        server.wait(timeout=10)
