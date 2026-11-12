from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import httpx
import jwt
from jwt import PyJWKSet

JWKS_TTL_SECONDS = 600
ALGORITHMS = ["RS256", "ES256", "PS256"]
SCOPES_HEADER = "x-arga-scopes"


@dataclass(frozen=True)
class Caller:
    subject: str
    scopes: tuple[str, ...]


@dataclass
class OAuth:
    issuer: str
    audience: str
    jwks_url: str
    client: httpx.AsyncClient
    _keys: PyJWKSet | None = field(default=None, repr=False)
    _fetched_at: float = 0.0

    @property
    def metadata_url(self) -> str:
        resource = httpx.URL(self.audience)
        path = f"/.well-known/oauth-protected-resource{resource.path}"
        return str(resource.copy_with(path=path))

    def protected_resource_metadata(self, scopes: list[str]) -> dict:
        metadata = {
            "resource": self.audience,
            "authorization_servers": [self.issuer],
            "bearer_methods_supported": ["header"],
        }
        if scopes:
            metadata["scopes_supported"] = scopes
        return metadata

    def challenge(self, scopes: list[str]) -> str:
        scope = f', scope="{" ".join(scopes)}"' if scopes else ""
        return f'Bearer error="invalid_token", resource_metadata="{self.metadata_url}"{scope}'

    async def _jwks(self, force: bool = False) -> PyJWKSet:
        fresh = time.monotonic() - self._fetched_at < JWKS_TTL_SECONDS
        if self._keys is None or force or not fresh:
            response = await self.client.get(self.jwks_url, timeout=5.0)
            response.raise_for_status()
            self._keys = PyJWKSet.from_dict(response.json())
            self._fetched_at = time.monotonic()
        return self._keys

    async def _key_for(self, token: str):
        kid = jwt.get_unverified_header(token).get("kid")
        for force in (False, True):
            for key in (await self._jwks(force=force)).keys:
                if key.key_id == kid:
                    return key.key
        return None

    async def caller(self, authorization: str | None) -> Caller | None:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        try:
            key = await self._key_for(token)
            if key is None:
                return None
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, ValueError):
            return None
        return Caller(str(claims["sub"]), tuple(str(claims.get("scope", "")).split()))


def from_environment(client: httpx.AsyncClient) -> OAuth | None:
    names = ("OAUTH_ISSUER", "MCP_RESOURCE_URL", "OAUTH_JWKS_URL")
    issuer, audience, jwks_url = (os.environ.get(name, "").strip() for name in names)
    if not (issuer and audience and jwks_url):
        return None
    return OAuth(issuer, audience, jwks_url, client)
