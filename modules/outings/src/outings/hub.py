from __future__ import annotations

import os
from typing import Any

import httpx

from arga_tenancy import kernel_url, user_headers

MODULE = "outings"


def timeout() -> float:
    return float(os.environ.get("PLACES_SEARCH_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def ask(
    capability: str, body: dict[str, Any], seconds: float | None = None
) -> httpx.Response:
    async with httpx.AsyncClient(transport=transport()) as client:
        return await client.post(
            f"{kernel_url()}/internal/capabilities/{capability}",
            json=body,
            headers={**user_headers(), "x-arga-module": MODULE},
            timeout=seconds or timeout(),
        )


async def search(query: str, limit: int = 6) -> dict[str, Any]:
    try:
        response = await ask("places.search", {"query": query, "limit": limit})
        if response.status_code == 200:
            return response.json()
        reason = f"Hub contesta {response.status_code}"
    except httpx.HTTPError as error:
        reason = f"Hub no contesta ({type(error).__name__})"
    return {"candidates": [], "failed": [{"source": "nominatim", "reason": reason}]}


class Refused(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


async def capability(name: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await ask(name, body)
    except httpx.HTTPError as error:
        raise Refused(f"Hub no contesta ({type(error).__name__})", 503) from error
    if response.status_code == 200:
        return response.json()
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    if response.status_code in (409, 422) and isinstance(detail, str):
        raise Refused(detail, response.status_code)
    raise Refused(f"Hub contesta {response.status_code}", 502)


async def catalogue() -> dict[str, Any]:
    return await capability("sources.catalogue", {})


async def plug(provider: str, label: str, params: dict[str, Any]) -> dict[str, Any]:
    return await capability(
        "sources.plug", {"provider": provider, "label": label, "params": params, "settings": {}}
    )


async def unplug(connection_id: str) -> bool:
    return bool((await capability("sources.unplug", {"connection": connection_id}))["removed"])


def photo_timeout() -> float:
    return float(os.environ.get("PLACE_PHOTO_TIMEOUT_SECONDS", "60"))


async def place_photo(body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await ask("places.photo", body, photo_timeout())
    except httpx.HTTPError as error:
        raise Refused(f"Hub no contesta ({type(error).__name__})", 503) from error
    if response.status_code != 200:
        raise Refused(f"Hub contesta {response.status_code}", 502)
    answer = response.json()
    if answer.get("failed"):
        raise Refused(str(answer["failed"]), 502)
    return answer
