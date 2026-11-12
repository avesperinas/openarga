from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

TEAM = "black-grass-396c.cloudflareaccess.com"
AUD = "7dc890e57e09976ac7bacf76257085d7bc9cca45465eb8ca413084b1fa90ffd2"
ME = "yo@ejemplo.com"
KID = "test-key-1"
CERTS_PATH = "/cdn-cgi/access/certs"

signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks() -> dict:
    public = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    return {"keys": [{**public, "kid": KID, "alg": "RS256", "use": "sig"}]}


def token(
    *,
    audience: str = AUD,
    issuer: str = f"https://{TEAM}",
    email: str | None = ME,
    key=None,
    kid: str = KID,
    expires_in: int = 3600,
) -> str:
    claims: dict = {
        "aud": [audience],
        "iss": issuer,
        "exp": int(time.time()) + expires_in,
        "iat": int(time.time()),
        "sub": "abc123",
    }
    if email is not None:
        claims["email"] = email
    return jwt.encode(claims, key or signing_key, algorithm="RS256", headers={"kid": kid})


PUBLIC_URL = "https://arga.test"
REALM_ISSUER = f"{PUBLIC_URL}/auth/realms/arga"
REALM_INTERNAL = "http://auth:8080/auth/realms/arga"
CLIENT_ID = "arga-web"
CLIENT_SECRET = "secreto-del-cliente-de-prueba"
SESSION_SECRET = "secreto-de-sesion-de-prueba-con-longitud-suficiente"
SUB = "0f8e2b6a-3c1d-4e5f-8a9b-7c6d5e4f3a2b"
USER = "9c1e4b7a-2d3f-4a5b-8c6d-1e2f3a4b5c6d"


def login_environment(monkeypatch) -> None:
    monkeypatch.setenv("OAUTH_ISSUER", REALM_ISSUER)
    monkeypatch.setenv("OIDC_INTERNAL_URL", REALM_INTERNAL)
    monkeypatch.setenv("OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("OIDC_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("PUBLIC_URL", PUBLIC_URL)
    monkeypatch.setenv("SESSION_SECRET", SESSION_SECRET)


def install_login(app, client) -> None:
    from gateway import oidc, people, session

    app.state.oidc = oidc.from_environment(client)
    app.state.sessions = session.from_environment(app.state.oidc)
    app.state.people = people.People(client, "http://kernel:8000")


def session_cookie(
    subject: str = SUB,
    *,
    expires_in: int = 900,
    refresh_token: str = "refresco-1",
    refresh_expires_in: int = 3600,
    secret: str = SESSION_SECRET,
) -> str:
    from dataclasses import asdict

    from gateway.session import COOKIE, Sealer, Session

    now = int(time.time())
    session = Session(subject, now + expires_in, refresh_token, now + refresh_expires_in)
    return Sealer(secret).seal(COOKIE, asdict(session))
