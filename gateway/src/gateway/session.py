from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from gateway.oidc import Challenge, Oidc, Rejected, Tokens, Unreachable

COOKIE = "__Host-arga_session"
LOGIN_COOKIE = "__Host-arga_login"
MAX_AGE = 90 * 86400
LOGIN_MAX_AGE = 600
SKEW_SECONDS = 30
GRACE_SECONDS = 300
REFRESH_REUSE_SECONDS = 60
MIN_SECRET_LENGTH = 32
VERSION = "v1"


class NotConfigured(RuntimeError):
    pass


class NoSession(Exception):
    pass


class Unverifiable(Exception):
    pass


class Sealer:
    def __init__(self, secret: str):
        if len(secret) < MIN_SECRET_LENGTH:
            raise NotConfigured(
                f"SESSION_SECRET tiene que tener al menos {MIN_SECRET_LENGTH} caracteres"
            )
        key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"arga gateway cookies"
        ).derive(secret.encode())
        self._aead = AESGCM(key)

    def seal(self, name: str, payload: dict) -> str:
        nonce = os.urandom(12)
        sealed = self._aead.encrypt(nonce, json.dumps(payload).encode(), name.encode())
        return f"{VERSION}.{base64.urlsafe_b64encode(nonce + sealed).rstrip(b'=').decode()}"

    def open(self, name: str, value: str | None) -> dict | None:
        if not value or not value.startswith(f"{VERSION}."):
            return None
        try:
            raw = value[len(VERSION) + 1 :]
            blob = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            plain = self._aead.decrypt(blob[:12], blob[12:], name.encode())
            payload = json.loads(plain)
        except (ValueError, InvalidTag):
            return None
        return payload if isinstance(payload, dict) else None


@dataclass(frozen=True)
class Session:
    subject: str
    expires_at: int
    refresh_token: str
    refresh_expires_at: int

    @classmethod
    def from_tokens(cls, subject: str, tokens: Tokens) -> Session:
        return cls(
            subject, tokens.access_expires_at, tokens.refresh_token, tokens.refresh_expires_at
        )


@dataclass(frozen=True)
class Resolved:
    subject: str
    cookie: str | None = None


@dataclass(frozen=True)
class PendingLogin:
    challenge: Challenge
    next: str


def cookie_header(name: str, value: str, max_age: int) -> str:
    return f"{name}={value}; Max-Age={max_age}; Path=/; Secure; HttpOnly; SameSite=Lax"


def expired_cookie_header(name: str) -> str:
    return cookie_header(name, "", 0)


class Sessions:
    def __init__(self, sealer: Sealer, oidc: Oidc):
        self.sealer = sealer
        self.oidc = oidc
        self._refreshing: dict[str, tuple[float, asyncio.Task[Tokens]]] = {}

    def issue(self, session: Session) -> str:
        return cookie_header(COOKIE, self.sealer.seal(COOKIE, asdict(session)), MAX_AGE)

    def read(self, value: str | None) -> Session | None:
        payload = self.sealer.open(COOKIE, value)
        if payload is None:
            return None
        try:
            return Session(**payload)
        except TypeError:
            return None

    async def resolve(self, value: str | None, now: float | None = None) -> Resolved:
        session = self.read(value)
        if session is None:
            raise NoSession("no session")
        now = time.time() if now is None else now
        if now < session.expires_at - SKEW_SECONDS:
            return Resolved(session.subject)
        if now >= session.refresh_expires_at:
            raise NoSession("the session is over")
        try:
            tokens = await self._refresh(session.refresh_token)
        except Rejected as error:
            raise NoSession(f"the realm no longer recognises this session: {error}") from error
        except Unreachable as error:
            if now < session.expires_at + GRACE_SECONDS:
                return Resolved(session.subject)
            raise Unverifiable(str(error)) from error
        return Resolved(session.subject, self.issue(Session.from_tokens(session.subject, tokens)))

    async def _refresh(self, refresh_token: str) -> Tokens:
        key = hashlib.sha256(refresh_token.encode()).hexdigest()
        now = time.monotonic()
        for stale in [
            k for k, (at, _) in self._refreshing.items() if now - at > REFRESH_REUSE_SECONDS
        ]:
            del self._refreshing[stale]
        entry = self._refreshing.get(key)
        if entry is None:
            entry = (now, asyncio.ensure_future(self.oidc.refresh(refresh_token)))
            self._refreshing[key] = entry
        try:
            return await asyncio.shield(entry[1])
        except Unreachable:
            self._refreshing.pop(key, None)
            raise

    def begin_login(self, next_path: str) -> tuple[Challenge, str]:
        challenge = Challenge.new()
        payload = {
            "state": challenge.state,
            "verifier": challenge.verifier,
            "nonce": challenge.nonce,
            "next": next_path,
        }
        value = self.sealer.seal(LOGIN_COOKIE, payload)
        return challenge, cookie_header(LOGIN_COOKIE, value, LOGIN_MAX_AGE)

    def pending_login(self, value: str | None) -> PendingLogin | None:
        payload = self.sealer.open(LOGIN_COOKIE, value)
        try:
            challenge = Challenge(payload["state"], payload["verifier"], payload["nonce"])
            return PendingLogin(challenge, str(payload["next"]))
        except (TypeError, KeyError):
            return None


def secrets_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith(("//", "/\\")):
        return "/"
    if any(ord(character) < 0x20 for character in value):
        return "/"
    return value


def from_environment(oidc: Oidc) -> Sessions:
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if not secret:
        raise NotConfigured(
            "falta SESSION_SECRET. El gateway no arranca sin poder cifrar sesiones."
        )
    return Sessions(Sealer(secret), oidc)
