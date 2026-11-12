from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from arga_module import hub

MODULE = "library"
SOURCES = ("openlibrary", "google_books")


def timeout() -> float:
    return float(os.environ.get("BOOK_SEARCH_TIMEOUT_SECONDS", "30"))


async def ask(client: httpx.AsyncClient, capability: str, body: dict[str, Any]) -> httpx.Response:
    return await hub.ask(client, MODULE, capability, body, timeout())


async def search(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    try:
        response = await ask(client, "books.search", {"query": query})
        if response.status_code == 200:
            return response.json()
        reason = f"Hub contesta {response.status_code}"
    except httpx.HTTPError as error:
        reason = f"Hub no contesta ({type(error).__name__})"
    return {"candidates": [], "failed": [{"source": name, "reason": reason} for name in SOURCES]}


async def cover(client: httpx.AsyncClient, source: str, ref: str) -> tuple[bytes, str] | None:
    try:
        response = await ask(client, "books.cover", {"source": source, "ref": ref})
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    found = response.json()
    if not found.get("cover") or found.get("type") not in COVER_TYPES:
        return None
    return base64.b64decode(found["cover"]), found["type"]


COVER_TYPES = ("image/jpeg", "image/png", "image/webp")
