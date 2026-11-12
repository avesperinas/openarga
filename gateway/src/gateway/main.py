from __future__ import annotations

import os
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask

from gateway import compress
from gateway import oauth as oauth_module
from gateway import oidc as oidc_module
from gateway import people as people_module
from gateway import privacy as privacy_module
from gateway import session as session_module
from gateway.flight import Flight
from gateway.session import COOKIE, LOGIN_COOKIE, NoSession, Resolved, Unverifiable

SERVICE = "gateway"
SUBJECT_HEADER = "x-arga-subject"

HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "host",
    }
)

NEVER_FORWARDED = HOP_BY_HOP | {
    SUBJECT_HEADER,
    people_module.USER_HEADER,
    people_module.SPACES_HEADER,
    *people_module.PREFERENCE_HEADERS.values(),
    oauth_module.SCOPES_HEADER,
}

ACCEPT_ENCODING = "accept-encoding"

OWN_COOKIES = frozenset({COOKIE, LOGIN_COOKIE})

PUBLIC = ("/healthz", "/version", "/privacidad")

INSTALL_ASSETS = frozenset(
    {
        "/apple-touch-icon.png",
        "/icon-192.png",
        "/icon-512.png",
        "/icon.svg",
        "/manifest.webmanifest",
        "/sw.js",
    }
)

PUSH_MODULE = "hub"
PUSH_PREFIX = "push/"

KERNEL = "kernel"


def kernel_url() -> str:
    return os.environ.get("KERNEL_URL", "http://kernel:8000").rstrip("/")


def shell_url() -> str:
    return os.environ.get("SHELL_URL", "http://shell:3000").rstrip("/")


def mcp_url() -> str:
    return os.environ.get("MCP_URL", "http://mcp:8000").rstrip("/")


def auth_url() -> str:
    return os.environ.get("AUTH_URL", "http://auth:8080").rstrip("/")


PUBLIC_REALM = "arga"


def client() -> httpx.AsyncClient:
    return app.state.client


LIMITS = httpx.Limits(max_connections=200, max_keepalive_connections=100, keepalive_expiry=4.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), limits=LIMITS)
    app.state.oauth = oauth_module.from_environment(app.state.client)
    app.state.people = people_module.People(app.state.client, kernel_url())
    app.state.oidc = oidc_module.from_environment(app.state.client)
    app.state.sessions = session_module.from_environment(app.state.oidc)
    yield
    await app.state.client.aclose()


app = FastAPI(title="OpenArga gateway", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {"service": SERVICE, "version": os.environ.get("APP_VERSION", "dev")}


@app.get("/privacidad", include_in_schema=False)
async def privacy() -> HTMLResponse:
    return HTMLResponse(privacy_module.PAGE)


async def person(request: Request) -> Resolved:
    return await request.app.state.sessions.resolve(request.cookies.get(COOKIE))


def navigating(request: Request) -> bool:
    if request.method not in ("GET", "HEAD"):
        return False
    mode = request.headers.get("sec-fetch-mode")
    if mode is not None:
        return mode == "navigate"
    return "text/html" in request.headers.get("accept", "")


def refuse(request: Request, error: Exception) -> Response:
    if isinstance(error, Unverifiable):
        return JSONResponse(
            status_code=503,
            content={"detail": "no se puede comprobar la sesión ahora mismo; prueba en un momento"},
        )
    if navigating(request):
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        login = httpx.URL("/login", params={"next": target})
        return RedirectResponse(str(login), status_code=302)
    return JSONResponse(
        status_code=401,
        content={"detail": f"hace falta iniciar sesión: {error}", "login": "/login"},
    )


def with_cookie(response: Response, cookie: str | None) -> Response:
    if cookie is not None:
        response.headers.append("set-cookie", cookie)
    return response


def without_own_cookies(value: bytes) -> bytes:
    kept = [
        part
        for part in value.decode("latin-1").split(";")
        if part.strip().partition("=")[0] not in OWN_COOKIES
    ]
    return ";".join(kept).strip().encode("latin-1")


async def forward(
    request: Request,
    upstream: str,
    path: str,
    subject: str | None,
    scopes: tuple[str, ...] | None = None,
) -> Response:
    started = time.perf_counter()
    url = httpx.URL(f"{upstream}/{path.lstrip('/')}", query=request.url.query.encode())
    headers = [
        (key, value)
        for key, value in request.headers.raw
        if key.decode().lower() not in NEVER_FORWARDED
    ]
    headers = [
        (key, without_own_cookies(value) if key.decode().lower() == "cookie" else value)
        for key, value in headers
    ]
    headers = [(key, value) for key, value in headers if value or key.decode().lower() != "cookie"]
    headers = [(key, value) for key, value in headers if key.decode().lower() != ACCEPT_ENCODING]
    headers.append((ACCEPT_ENCODING.encode(), b"identity"))
    if subject is not None:
        headers.append((SUBJECT_HEADER.encode(), subject.encode()))
        person = await request.app.state.people.person_for(subject)
        if person is not None:
            headers.extend(person.headers())
    if scopes is not None:
        headers.append((oauth_module.SCOPES_HEADER.encode(), " ".join(scopes).encode()))

    proxied = client().build_request(request.method, url, headers=headers, content=request.stream())
    try:
        response = await client().send(proxied, stream=True)
    except httpx.ConnectError:
        return JSONResponse(
            status_code=502,
            content={"detail": f"{upstream} is not answering"},
        )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"detail": f"{upstream} timed out"})

    headers_out = {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() not in HOP_BY_HOP
    }
    headers_out[TIMING_HEADER] = with_gateway_timing(
        headers_out.get(TIMING_HEADER), time.perf_counter() - started
    )
    body = response.aiter_raw()
    if compress.worth(request.method, response.status_code, response.headers):
        encoding = compress.negotiate(request.headers.get(ACCEPT_ENCODING))
        compress.vary(headers_out)
        if encoding is not None:
            compress.label(headers_out, encoding)
            body = compress.encoded(body, encoding)
    return StreamingResponse(
        body,
        status_code=response.status_code,
        headers=headers_out,
        background=BackgroundTask(response.aclose),
    )


TIMING_HEADER = "server-timing"


def with_gateway_timing(upstream: str | None, seconds: float) -> str:
    own = f"gw;dur={seconds * 1000:.1f}"
    return f"{upstream}, {own}" if upstream else own


MODULE_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")

MODULES_TTL_SECONDS = 30


def flight(state) -> Flight:
    found = getattr(state, "flight", None)
    if found is None:
        found = state.flight = Flight()
    return found


def module_url(module_id: str) -> str:
    template = os.environ.get("MODULE_URL_TEMPLATE", "http://{module}:8000")
    return template.format(module=module_id)


async def remote_scopes(state) -> list[str]:
    cache = getattr(state, "remote_scopes", None)
    if cache is not None and time.monotonic() - cache[0] < MODULES_TTL_SECONDS:
        return cache[1]
    return await flight(state).run("remote_scopes", lambda: ask_remote_scopes(state))


async def ask_remote_scopes(state) -> list[str]:
    try:
        response = await state.client.get(f"{kernel_url()}/tools", timeout=5.0)
        response.raise_for_status()
        scopes = sorted(
            {tool["scope"] for tool in response.json() if tool["scope"].endswith(":read")}
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []
    state.remote_scopes = (time.monotonic(), scopes)
    return scopes


async def registry(state) -> tuple[set[str], dict[str, str]] | None:
    cache = getattr(state, "modules", None)
    if cache is not None and time.monotonic() - cache[0] < MODULES_TTL_SECONDS:
        return cache[1], (cache[2] if len(cache) > 2 else {})
    return await flight(state).run("modules", lambda: ask_registry(state))


async def ask_registry(state) -> tuple[set[str], dict[str, str]] | None:
    try:
        response = await state.client.get(f"{kernel_url()}/modules", timeout=5.0)
        response.raise_for_status()
        rows = [row for row in response.json() if row.get("enabled", True)]
        known = {row["id"] for row in rows}
        views = {
            str(row["view"]).strip("/"): row["id"]
            for row in rows
            if isinstance(row.get("view"), str) and row["view"].strip("/")
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return None
    state.modules = (time.monotonic(), known, views)
    return known, views


async def installed(state, module_id: str) -> bool:
    if not MODULE_ID.match(module_id):
        return False
    found = await registry(state)
    return found is not None and module_id in found[0]


async def app_of(state, first: str) -> str | None:
    if not MODULE_ID.match(first):
        return None
    found = await registry(state)
    if found is None:
        return None
    known, views = found
    if first in views:
        return views[first]
    return first if first in known else None


METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


@app.api_route("/mcp", methods=METHODS, include_in_schema=False)
async def mcp(request: Request) -> Response:
    oauth = request.app.state.oauth
    if oauth is None:
        return JSONResponse(
            status_code=503, content={"detail": "el servidor de autorización no está configurado"}
        )
    caller = await oauth.caller(request.headers.get("authorization"))
    if caller is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "hace falta un token del servidor de autorización"},
            headers={"www-authenticate": oauth.challenge(await remote_scopes(request.app.state))},
        )
    return await forward(request, mcp_url(), "/mcp", caller.subject, caller.scopes)


@app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
async def protected_resource(request: Request) -> Response:
    oauth = request.app.state.oauth
    if oauth is None:
        return JSONResponse(status_code=404, content={"detail": "not found"})
    return JSONResponse(oauth.protected_resource_metadata(await remote_scopes(request.app.state)))


@app.get("/.well-known/{kind}/auth/realms/{realm}", include_in_schema=False)
async def authorization_server_metadata(request: Request, kind: str, realm: str) -> Response:
    if realm != PUBLIC_REALM or kind not in ("oauth-authorization-server", "openid-configuration"):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    return await forward(request, auth_url(), f"/auth/realms/{realm}/.well-known/{kind}", None)


@app.api_route("/auth/{path:path}", methods=METHODS, include_in_schema=False)
async def authorization_server(request: Request, path: str) -> Response:
    if not (path.startswith(f"realms/{PUBLIC_REALM}/") or path.startswith("resources/")):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    return await forward(request, auth_url(), f"/auth/{path}", None)


def page(
    title: str, message: str, link: str, label: str, status_code: int = 200, script: str = ""
) -> HTMLResponse:
    tail = f"<script>{script}</script>" if script else ""
    body = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title} · arga</title></head><body><h1>{title}</h1><p>{message}</p>"
        f'<p><a href="{link}">{label}</a></p>{tail}</body></html>'
    )
    return HTMLResponse(body, status_code=status_code, headers={"cache-control": "no-store"})


@app.get("/login", include_in_schema=False)
async def login(request: Request, next: str | None = None) -> Response:
    target = session_module.safe_next(next)
    sessions = request.app.state.sessions
    if sessions.read(request.cookies.get(COOKIE)) is not None:
        try:
            who = await person(request)
            return with_cookie(RedirectResponse(target, status_code=302), who.cookie)
        except (NoSession, Unverifiable):
            pass
    challenge, cookie = sessions.begin_login(target)
    response = RedirectResponse(request.app.state.oidc.authorization_url(challenge), 302)
    response.headers["cache-control"] = "no-store"
    return with_cookie(response, cookie)


@app.get("/login/callback", include_in_schema=False)
async def login_callback(
    request: Request, code: str | None = None, state: str | None = None
) -> Response:
    sessions = request.app.state.sessions
    oidc = request.app.state.oidc
    pending = sessions.pending_login(request.cookies.get(LOGIN_COOKIE))
    again = "/login"
    if pending is None or not state or not code:
        return page(
            "No se pudo terminar de entrar",
            "El inicio de sesión caducó o empezó en otra ventana.",
            again,
            "Volver a entrar",
            status_code=400,
        )
    again = str(httpx.URL("/login", params={"next": pending.next}))
    if not session_module.secrets_equal(state, pending.challenge.state):
        return page(
            "No se pudo terminar de entrar",
            "Esta respuesta no corresponde a tu inicio de sesión.",
            again,
            "Volver a entrar",
            status_code=400,
        )
    try:
        tokens = await oidc.exchange(code, pending.challenge)
        if tokens.id_token is None:
            raise oidc_module.Rejected("no id_token")
        identity = await oidc.identity(tokens.id_token, pending.challenge)
    except oidc_module.Rejected:
        return page(
            "No se pudo terminar de entrar",
            "El servidor de autorización no aceptó este inicio de sesión.",
            again,
            "Volver a entrar",
            status_code=400,
        )
    except oidc_module.Unreachable:
        return page(
            "No se pudo terminar de entrar",
            "El servidor de autorización no contesta. Prueba en un momento.",
            again,
            "Volver a entrar",
            status_code=503,
        )

    await request.app.state.people.id_for(identity.subject)
    session = session_module.Session.from_tokens(identity.subject, tokens)
    response = RedirectResponse(pending.next, status_code=302)
    response.headers["cache-control"] = "no-store"
    response.headers.append("set-cookie", sessions.issue(session))
    response.headers.append("set-cookie", session_module.expired_cookie_header(LOGIN_COOKIE))
    return response


CLEAR_SITE_DATA = '"cache", "storage"'
FORGET_HERE = (
    "(async()=>{try{localStorage.clear();sessionStorage.clear()}catch(e){}"
    "try{for(const d of await indexedDB.databases())if(d.name)indexedDB.deleteDatabase(d.name)}"
    "catch(e){}"
    "try{for(const k of await caches.keys())await caches.delete(k)}catch(e){}"
    "try{for(const r of await navigator.serviceWorker.getRegistrations())await r.unregister()}"
    "catch(e){}})()"
)


@app.api_route("/logout", methods=["GET", "POST"], include_in_schema=False)
async def logout(request: Request) -> Response:
    sessions = request.app.state.sessions
    session = sessions.read(request.cookies.get(COOKIE))
    if session is not None:
        await request.app.state.oidc.revoke(session.refresh_token)
    response = page(
        "Has salido de arga",
        "Tu sesión está cerrada y lo guardado en este dispositivo, borrado.",
        "/login",
        "Entrar",
        script=FORGET_HERE,
    )
    response.headers.append("set-cookie", session_module.expired_cookie_header(COOKIE))
    response.headers["clear-site-data"] = CLEAR_SITE_DATA
    return response


def changes_person(method: str, path: str) -> bool:
    return method not in ("GET", "HEAD", "OPTIONS") and (
        path in ("spaces", "me/preferences") or path.startswith("spaces/")
    )


@app.api_route(
    "/api/{module_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
async def api(request: Request, module_id: str, path: str) -> Response:
    if module_id == PUSH_MODULE and request.method == "POST" and path.startswith(PUSH_PREFIX):
        if not await installed(request.app.state, module_id):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        return await forward(request, module_url(module_id), path, None)
    try:
        who = await person(request)
    except (NoSession, Unverifiable) as error:
        return refuse(request, error)

    if module_id == KERNEL:
        if path == "internal" or path.startswith("internal/"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        response = await forward(request, kernel_url(), path, who.subject)
        if changes_person(request.method, path) and response.status_code < 300:
            request.app.state.people.forget(who.subject)
        return with_cookie(response, who.cookie)

    if not await installed(request.app.state, module_id):
        return JSONResponse(
            status_code=404,
            content={"detail": f"module '{module_id}' is not installed"},
        )

    return with_cookie(await forward(request, module_url(module_id), path, who.subject), who.cookie)


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
async def shell(request: Request, path: str) -> Response:
    first, _, rest = path.partition("/")
    owner = await app_of(request.app.state, first) if first != KERNEL else None
    if owner is not None:
        return await module_app(request, owner, path, f"/{rest}")

    if request.method in ("GET", "HEAD") and request.url.path in INSTALL_ASSETS:
        return await forward(request, shell_url(), path, None)
    try:
        who = await person(request)
    except (NoSession, Unverifiable) as error:
        return refuse(request, error)

    return with_cookie(await forward(request, shell_url(), path, who.subject), who.cookie)


async def module_app(request: Request, module_id: str, path: str, inner: str) -> Response:
    if request.method in ("GET", "HEAD") and inner in INSTALL_ASSETS:
        return await forward(request, module_url(module_id), path, None)
    try:
        who = await person(request)
    except (NoSession, Unverifiable) as error:
        return refuse(request, error)
    return with_cookie(await forward(request, module_url(module_id), path, who.subject), who.cookie)
