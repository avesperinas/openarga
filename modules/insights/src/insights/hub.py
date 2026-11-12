from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from arga_tenancy import kernel_url, user_headers

MODULE = "insights"
COVER_TYPES = ("image/jpeg", "image/png", "image/webp")


class Unavailable(Exception):
    pass


def timeout() -> float:
    return float(os.environ.get("HUB_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def ask(capability: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{capability}",
                json=body,
                headers={**user_headers(), "x-arga-module": MODULE},
                timeout=timeout(),
            )
    except httpx.HTTPError as error:
        raise Unavailable(f"el kernel no contesta ({type(error).__name__})") from error
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise Unavailable(str(detail or f"{capability} contesta {response.status_code}"))
    return response.json()


async def books(query: str, limit: int = 5) -> list[dict[str, Any]]:
    return list((await ask("books.search", {"query": query, "limit": limit})).get("candidates", []))


async def cover(source: str, ref: str) -> tuple[bytes, str] | None:
    try:
        found = await ask("books.cover", {"source": source, "ref": ref})
    except Unavailable:
        return None
    if not found.get("cover") or found.get("type") not in COVER_TYPES:
        return None
    return base64.b64decode(found["cover"]), found["type"]


async def podcasts(query: str, kind: str, limit: int = 5) -> list[dict[str, Any]]:
    answer = await ask("podcasts.search", {"query": query, "kind": kind, "limit": limit})
    return list(answer.get("candidates", []))


async def films(query: str, kind: str, limit: int = 5) -> list[dict[str, Any]]:
    answer = await ask("films.search", {"query": query, "kind": kind, "limit": limit})
    return list(answer.get("candidates", []))


async def want_book(body: dict[str, Any]) -> dict[str, Any]:
    return await ask("books.want", body)
