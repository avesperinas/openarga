from __future__ import annotations

import json
import os
from contextvars import ContextVar
from functools import cache
from pathlib import Path

from starlette.types import ASGIApp, Receive, Scope, Send

CATALOGS = Path(__file__).resolve().parent / "i18n"
HEADER = b"x-arga-locale"

_locale: ContextVar[str | None] = ContextVar("kernel_locale", default=None)


@cache
def _catalog(locale: str) -> dict[str, str]:
    path = CATALOGS / f"{locale}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def locale() -> str:
    chosen = _locale.get() or os.environ.get("OPENARGA_LOCALE", "en")
    return chosen.split("-")[0].lower()


def say(key: str, **values: object) -> str:
    template = _catalog(locale()).get(key) or _catalog("en").get(key) or key
    return template.format(**values)


class Language:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sent = dict(scope.get("headers") or []).get(HEADER)
        token = _locale.set(sent.decode("latin-1") if sent else None)
        try:
            await self.app(scope, receive, send)
        finally:
            _locale.reset(token)
