from __future__ import annotations

from typing import Any

import httpx

from arga_tenancy import kernel_url, user_headers

MODULE_HEADER = "x-arga-module"


async def ask(
    client: httpx.AsyncClient,
    module: str,
    capability: str,
    body: dict[str, Any],
    seconds: float = 30.0,
) -> httpx.Response:
    return await client.post(
        f"{kernel_url()}/internal/capabilities/{capability}",
        json=body,
        headers={**user_headers(), MODULE_HEADER: module},
        timeout=seconds,
    )
