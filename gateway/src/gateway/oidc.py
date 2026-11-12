from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import secrets
import time
from dataclasses import dataclass, field

import httpx
import jwt
from jwt import PyJWKSet

JWKS_TTL_SECONDS = 600
ALGORITHMS = ["RS256", "ES256", "PS256"]


class NotConfigured(RuntimeError):
    pass


class Rejected(Exception):
    pass


class Unreachable(Exception):
    pass


@dataclass(frozen=True)
class Tokens:
    access_expires_at: int
    refresh_token: str
    refresh_expires_at: int
    id_token: str | None


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str | None
    email_verified: bool


@dataclass(frozen=True)
class Challenge:
    state: str
    verifier: str
    nonce: str

    @classmethod
    def new(cls) -> Challenge:
        return cls(secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(32))

    @property
    def code_challenge(self) -> str:
        digest = hashlib.sha256(self.verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@dataclass
class Oidc:
    issuer: str
    internal: str
    client_id: str
    client_secret: str
    public_url: str
    client: httpx.AsyncClient
    idp_hint: str = "google"
    _keys: PyJWKSet | None = field(default=None, repr=False)
    _fetched_at: float = 0.0

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_url}/login/callback"

    def authorization_url(self, challenge: Challenge) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": self.redirect_uri,
            "state": challenge.state,
            "nonce": challenge.nonce,
            "code_challenge": challenge.code_challenge,
            "code_challenge_method": "S256",
        }
        if self.idp_hint:
            params["kc_idp_hint"] = self.idp_hint
        url = httpx.URL(f"{self.issuer}/protocol/openid-connect/auth", params=params)
        return str(url)

    async def _token(self, form: dict[str, str]) -> Tokens:
        try:
            response = await self.client.post(
                f"{self.internal}/protocol/openid-connect/token",
                data=form,
                auth=(self.client_id, self.client_secret),
                timeout=10.0,
            )
        except httpx.HTTPError as error:
            raise Unreachable(type(error).__name__) from error
        if response.status_code in (400, 401):
            try:
                raise Rejected(str(response.json().get("error", "rejected")))
            except (ValueError, AttributeError):
                raise Rejected("rejected") from None
        if response.status_code != 200:
            raise Unreachable(f"token endpoint answered {response.status_code}")
        now = int(time.time())
        try:
            body = response.json()
            return Tokens(
                access_expires_at=now + int(body["expires_in"]),
                refresh_token=str(body["refresh_token"]),
                refresh_expires_at=now + int(body.get("refresh_expires_in") or 90 * 86400),
                id_token=body.get("id_token"),
            )
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise Unreachable(f"malformed token response: {type(error).__name__}") from error

    async def exchange(self, code: str, challenge: Challenge) -> Tokens:
        return await self._token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": challenge.verifier,
            }
        )

    async def refresh(self, refresh_token: str) -> Tokens:
        return await self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    async def revoke(self, refresh_token: str) -> None:
        with contextlib.suppress(httpx.HTTPError):
            await self.client.post(
                f"{self.internal}/protocol/openid-connect/logout",
                data={"refresh_token": refresh_token},
                auth=(self.client_id, self.client_secret),
                timeout=5.0,
            )

    async def _jwks(self, force: bool = False) -> PyJWKSet:
        fresh = time.monotonic() - self._fetched_at < JWKS_TTL_SECONDS
        if self._keys is None or force or not fresh:
            response = await self.client.get(
                f"{self.internal}/protocol/openid-connect/certs", timeout=5.0
            )
            response.raise_for_status()
            self._keys = PyJWKSet.from_dict(response.json())
            self._fetched_at = time.monotonic()
        return self._keys

    async def identity(self, id_token: str, challenge: Challenge) -> Identity:
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
            key = None
            for force in (False, True):
                key = next((k.key for k in (await self._jwks(force)).keys if k.key_id == kid), None)
                if key is not None:
                    break
            if key is None:
                raise Rejected("unknown signing key")
            claims = jwt.decode(
                id_token,
                key,
                algorithms=ALGORITHMS,
                audience=self.client_id,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub", "nonce"]},
            )
        except httpx.HTTPError as error:
            raise Unreachable(type(error).__name__) from error
        except jwt.PyJWTError as error:
            raise Rejected(str(error)) from error
        if not secrets.compare_digest(str(claims["nonce"]), challenge.nonce):
            raise Rejected("nonce mismatch")
        return Identity(
            subject=str(claims["sub"]),
            email=claims.get("email"),
            email_verified=claims.get("email_verified") is True,
        )


def from_environment(client: httpx.AsyncClient) -> Oidc:
    values = {
        name: os.environ.get(name, "").strip()
        for name in (
            "OAUTH_ISSUER",
            "OIDC_INTERNAL_URL",
            "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET",
            "PUBLIC_URL",
        )
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise NotConfigured(
            f"falta {', '.join(missing)}. El gateway no arranca sin login: una puerta sin "
            f"cerradura no es algo que ninguna sonda vaya a detectar."
        )
    return Oidc(
        issuer=values["OAUTH_ISSUER"].rstrip("/"),
        internal=values["OIDC_INTERNAL_URL"].rstrip("/"),
        client_id=values["OIDC_CLIENT_ID"],
        client_secret=values["OIDC_CLIENT_SECRET"],
        public_url=values["PUBLIC_URL"].rstrip("/"),
        client=client,
        idp_hint=os.environ.get("OIDC_IDP_HINT", "google").strip(),
    )
