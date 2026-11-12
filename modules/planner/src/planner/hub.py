from __future__ import annotations

import os
from typing import Any

import httpx

from arga_tenancy import kernel_url, user_headers

MODULE = "planner"


class Refused(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def timeout() -> float:
    return float(os.environ.get("HUB_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def ask(capability: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(transport=transport(), timeout=timeout()) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{capability}",
                json=body,
                headers={**user_headers(), "x-arga-module": MODULE},
            )
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


INLET = f"{MODULE}.calendar"


async def plug(
    provider: str, label: str, params: dict[str, Any], settings: dict[str, Any]
) -> dict[str, Any]:
    return await ask(
        "sources.plug",
        {"provider": provider, "label": label, "params": params, "settings": settings},
    )


async def catalogue() -> dict[str, Any]:
    return await ask("sources.catalogue", {})


async def unsubscribe(connection_id: str) -> bool:
    return bool((await ask("sources.unplug", {"connection": connection_id}))["removed"])


async def search(
    provider: str, question: str, query: str | None = None, parent: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"provider": provider, "ask": question}
    if query:
        body["query"] = query
    if parent:
        body["parent"] = parent
    return await ask("sources.search", body)
