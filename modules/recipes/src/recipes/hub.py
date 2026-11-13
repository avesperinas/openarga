from __future__ import annotations

import os
from typing import Any

import httpx

from arga_tenancy import kernel_url, user_headers

MODULE = "recipes"
SOURCES = ("usda", "off")


def timeout() -> float:
    return float(os.environ.get("FOOD_SEARCH_TIMEOUT_SECONDS", "30"))


async def ask(client: httpx.AsyncClient, capability: str, body: dict[str, Any]) -> httpx.Response:
    return await client.post(
        f"{kernel_url()}/internal/capabilities/{capability}",
        json=body,
        headers={**user_headers(), "x-arga-module": MODULE},
        timeout=timeout(),
    )


async def search(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    try:
        response = await ask(client, "food.search", {"query": query})
        if response.status_code == 200:
            return response.json()
        reason = f"Hub contesta {response.status_code}"
    except httpx.HTTPError as error:
        reason = f"Hub is not answering ({type(error).__name__})"
    return {"candidates": [], "failed": [{"source": name, "reason": reason} for name in SOURCES]}


def usda_key() -> str:
    return os.environ.get("USDA_API_KEY", "").strip()


async def hand_over_usda(client: httpx.AsyncClient) -> bool:
    key = usda_key()
    if not key:
        return True
    try:
        response = await ask(client, "usda.handoff", {"label": "USDA", "secrets": {"api_key": key}})
    except httpx.HTTPError:
        return False
    return response.status_code == 200
