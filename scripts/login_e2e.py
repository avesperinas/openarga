from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx

GATEWAY = "http://gateway:8000"
REALM = "http://auth:8080/auth/realms/arga"
SESSION = "__Host-arga_session"
NAVIGATE = {"sec-fetch-mode": "navigate", "accept": "text/html"}
JSON = {"sec-fetch-mode": "cors", "accept": "application/json"}

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FALLA'}  {name}{f'  ({detail})' if detail and not ok else ''}")
    if not ok:
        failures.append(name)


class Browser:
    def __init__(self, jar: dict | None = None) -> None:
        self.jar: dict[str, dict[str, str]] = jar or {}
        self.http = httpx.Client(timeout=30.0)

    def cookies(self, url: str) -> dict[str, str]:
        parsed = urlparse(url)
        stored = self.jar.get(parsed.netloc, {})
        matching = sorted(
            (key.split(" ", 1) for key in stored if parsed.path.startswith(key.split(" ", 1)[0])),
            key=lambda pair: len(pair[0]),
        )
        return {name: stored[f"{path} {name}"] for path, name in matching}

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        sent = self.cookies(url)
        if sent:
            headers["cookie"] = "; ".join(f"{k}={v}" for k, v in sent.items())
        response = self.http.request(method, url, headers=headers, **kwargs)
        stored = self.jar.setdefault(urlparse(url).netloc, {})
        for header in response.headers.get_list("set-cookie"):
            pair, _, attributes = header.partition(";")
            name, _, value = pair.strip().partition("=")
            path = "/"
            for attribute in attributes.split(";"):
                key, _, val = attribute.strip().partition("=")
                if key.lower() == "path" and val:
                    path = val
            expired = "max-age=0" in attributes.lower().replace(" ", "") or not value
            if expired:
                stored.pop(f"{path} {name}", None)
            else:
                stored[f"{path} {name}"] = value
        return response

    def follow(self, method: str, url: str, **kwargs) -> tuple[httpx.Response, list[str]]:
        hops = [url]
        response = self.request(method, url, **kwargs)
        while response.status_code in (301, 302, 303, 307) and len(hops) < 25:
            url = urljoin(url, response.headers["location"])
            hops.append(url)
            if not url.startswith("http://"):
                break
            if urlparse(url).netloc not in ("gateway:8000", "auth:8080"):
                break
            response = self.request("GET", url, headers=NAVIGATE)
        return response, hops

    def submit_login(self, page: httpx.Response, username: str, password: str):
        match = re.search(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', page.text)
        assert match, "no hay formulario de login en la página"
        action = unescape(match.group(1))
        return self.follow(
            "POST",
            action,
            data={"username": username, "password": password, "credentialId": ""},
            headers=NAVIGATE,
        )


def log_in(browser: Browser, username: str, next_path: str = "/api/kernel/ui/preferences"):
    page, hops = browser.follow("GET", f"{GATEWAY}/login?next={next_path}", headers=NAVIGATE)
    check(
        "el login lleva al IdP sin pasar por la pantalla del realm",
        "/realms/fake/" in hops[-1],
        f"{page.status_code} " + " → ".join(hops),
    )
    return browser.submit_login(page, username, "contraseña-de-prueba-1")


def phase_one(state: Path) -> None:
    anonymous = Browser()
    api = anonymous.request("GET", f"{GATEWAY}/api/kernel/ui/preferences", headers=JSON)
    check(
        "sin sesión, la API contesta 401 y JSON",
        api.status_code == 401 and api.headers["content-type"].startswith("application/json"),
        f"{api.status_code} {api.headers.get('content-type')}",
    )
    page = anonymous.request("GET", f"{GATEWAY}/training/hoy", headers=NAVIGATE)
    check(
        "sin sesión, una página va al login",
        page.status_code == 302 and page.headers["location"] == "/login?next=%2Ftraining%2Fhoy",
        f"{page.status_code} {page.headers.get('location')}",
    )
    for path, expected in (("/healthz", 200), ("/version", 200), ("/mcp", 401)):
        status = anonymous.request("GET", f"{GATEWAY}{path}").status_code
        check(f"{path} sigue dando {expected} sin sesión", status == expected, str(status))

    owner = Browser()
    final, hops = log_in(owner, "dueno@ejemplo.com")
    check(
        "la persona de la lista blanca vuelve al gateway con sesión",
        SESSION in owner.cookies(f"{GATEWAY}/")
        and hops[-1] == f"{GATEWAY}/api/kernel/ui/preferences",
        " → ".join(urlparse(h).netloc + urlparse(h).path for h in hops),
    )
    check("y el kernel le contesta", final.status_code == 200, str(final.status_code))
    written = owner.request(
        "PUT",
        f"{GATEWAY}/api/kernel/ui/desktops/mobile",
        json={"pages": [{"id": "p1", "items": []}], "updated_at": None},
        headers=JSON,
    )
    check("y lo que escribe llega al kernel", written.status_code == 200, str(written.status_code))
    internal = owner.request(
        "POST",
        f"{GATEWAY}/api/kernel/internal/users",
        json={"subject": "otro-sub"},
        headers=JSON,
    )
    check("con sesión, la API interna del kernel no se alcanza", internal.status_code == 404)

    intruder = Browser()
    final, hops = log_in(intruder, "intruso@ejemplo.com")
    check(
        "una cuenta del IdP fuera de la lista blanca no llega al gateway",
        SESSION not in intruder.cookies(f"{GATEWAY}/")
        and not any("/login/callback" in hop for hop in hops),
        " → ".join(hops),
    )
    check(
        "y el realm se lo dice",
        final.status_code in (200, 400, 401) and urlparse(hops[-1]).netloc == "auth:8080",
        f"{final.status_code} {hops[-1]}",
    )

    logout = owner.request("POST", f"{GATEWAY}/logout")
    after = owner.request("GET", f"{GATEWAY}/api/kernel/ui/preferences", headers=JSON)
    check(
        "salir borra la sesión",
        logout.status_code == 200
        and SESSION not in owner.cookies(f"{GATEWAY}/")
        and after.status_code == 401,
        f"{logout.status_code} {after.status_code}",
    )

    again = Browser()
    log_in(again, "dueno@ejemplo.com")
    ok = again.request("GET", f"{GATEWAY}/api/kernel/ui/preferences", headers=JSON)
    check("se puede volver a entrar", ok.status_code == 200, str(ok.status_code))
    (state / "jar.json").write_text(json.dumps(again.jar))
    claude(again)

    google = Browser()
    params = (
        "client_id=arga-web&response_type=code&scope=openid"
        f"&redirect_uri={GATEWAY}/login/callback&state=s&nonce=n&kc_idp_hint=google"
        "&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256"
    )
    _, hops = google.follow("GET", f"{REALM}/protocol/openid-connect/auth?{params}")
    to_google = [h for h in hops if urlparse(h).netloc == "accounts.google.com"]
    check(
        "con Google configurado, el realm manda a accounts.google.com",
        bool(to_google)
        and parse_qs(urlparse(to_google[0]).query).get("client_id") == ["id-de-google-de-prueba"],
        " → ".join(hops),
    )


def claude(browser: Browser) -> None:
    callback = "https://claude.ai/api/mcp/auth_callback"
    verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    query = urlencode(
        {
            "client_id": "claude",
            "response_type": "code",
            "redirect_uri": callback,
            "scope": "training:read",
            "state": "estado",
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
        }
    )
    _, hops = browser.follow(
        "GET", f"{REALM}/protocol/openid-connect/auth?{query}", headers=NAVIGATE
    )
    code = parse_qs(urlparse(hops[-1]).query).get("code", [""])[0]
    check(
        "Claude recibe su código sin volver a pedir login",
        hops[-1].startswith(callback) and bool(code),
        " → ".join(hops),
    )

    token_url = f"{REALM}/protocol/openid-connect/token"
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback,
        "client_id": "claude",
    }
    without_pkce = httpx.post(token_url, data=form)
    check(
        "sin el verificador de PKCE no hay token",
        without_pkce.status_code == 400,
        str(without_pkce.status_code),
    )

    _, hops = browser.follow(
        "GET", f"{REALM}/protocol/openid-connect/auth?{query}", headers=NAVIGATE
    )
    form["code"] = parse_qs(urlparse(hops[-1]).query).get("code", [""])[0]
    issued = httpx.post(token_url, data={**form, "code_verifier": verifier})
    check(
        "con PKCE y sin secreto, Claude tiene su token",
        issued.status_code == 200,
        issued.text[:200],
    )
    token = issued.json().get("access_token", "") if issued.status_code == 200 else ""
    response = httpx.get(f"{GATEWAY}/mcp", headers={"authorization": f"Bearer {token}"})
    check(
        "y el gateway lo deja pasar a /mcp", response.status_code != 401, str(response.status_code)
    )


def phase_two(state: Path) -> None:
    browser = Browser(json.loads((state / "jar.json").read_text()))
    time.sleep(40)
    response = browser.request("GET", f"{GATEWAY}/api/kernel/ui/preferences", headers=JSON)
    check(
        "deshabilitada en el realm, la sesión muere en el siguiente refresco",
        response.status_code == 401,
        str(response.status_code),
    )


if __name__ == "__main__":
    phase, directory = sys.argv[1], Path(sys.argv[2])
    {"uno": phase_one, "dos": phase_two}[phase](directory)
    if failures:
        print(f"{len(failures)} comprobación(es) fallida(s)")
        sys.exit(1)
