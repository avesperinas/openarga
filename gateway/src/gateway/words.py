from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

from starlette.requests import Request

CATALOGS = Path(__file__).resolve().parent / "i18n"


@cache
def _catalog(locale: str) -> dict[str, str]:
    path = CATALOGS / f"{locale}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def language(request: Request | None) -> str:
    wanted = request.headers.get("accept-language", "") if request is not None else ""
    for part in wanted.split(","):
        code = part.split(";")[0].strip().split("-")[0].lower()
        if code and _catalog(code):
            return code
    fallback = os.environ.get("OPENARGA_LOCALE", "en").split("-")[0].lower()
    return fallback if _catalog(fallback) else "en"


def say(request: Request | None, key: str) -> str:
    return _catalog(language(request)).get(key) or _catalog("en").get(key) or key
