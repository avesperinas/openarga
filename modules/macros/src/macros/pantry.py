from __future__ import annotations

import os
import re
import sys
from typing import Any

import httpx

import arga_contracts as contracts
from arga_tenancy import kernel_url, user_headers
from macros.common import NotFound, Unavailable

MODULE = "macros"


def timeout() -> float:
    return float(os.environ.get("PANTRY_TIMEOUT_SECONDS", "40"))


DOWN = "Recipes is not answering now. What you logged is still visible; try again in a moment."


async def ask(client: httpx.AsyncClient, service: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.post(
            f"{kernel_url()}/internal/capabilities/{service}",
            json=body,
            headers={**user_headers(), "x-arga-module": MODULE},
            timeout=timeout(),
        )
    except httpx.HTTPError as error:
        print(f"pantry · {service}: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        raise Unavailable(DOWN) from error
    if response.status_code == 404 and service == contracts.RECIPES_NUTRIENTS:
        raise NotFound("esa receta")
    if response.status_code >= 500:
        print(f"pantry · {service}: {response.status_code} {response.text[:300]}", file=sys.stderr)
        raise Unavailable(_said(response))
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise Unavailable(f"Recipes no contesta: {detail or response.status_code}")
    return response.json()


def _said(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if not isinstance(detail, str) or not detail.strip() or "contesta" in detail:
        return DOWN
    return f"Recipes no puede ahora: {re.sub(r' *[(][A-Za-z]+[)]', '', detail).strip()}"


async def search(client: httpx.AsyncClient, query: str, outside: bool = True) -> dict[str, Any]:
    return await ask(
        client,
        contracts.PANTRY_SEARCH,
        {"query": query, "limit": 8, "outside": outside, "enough": 1},
    )


async def foods(client: httpx.AsyncClient, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    found = await ask(client, contracts.PANTRY_NUTRIENTS, {"ids": sorted(set(ids))})
    return {one["id"]: one for one in found.get("foods", [])}


async def import_food(
    client: httpx.AsyncClient, source: str, source_ref: str, alias: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"source": source, "source_ref": source_ref}
    if alias:
        body["alias"] = alias
    return await ask(client, contracts.PANTRY_IMPORT, body)


async def recipes(client: httpx.AsyncClient, query: str) -> list[dict[str, Any]]:
    found = await ask(client, contracts.RECIPES_SEARCH, {"query": query, "limit": 8})
    return found.get("recipes", [])


async def recipe(client: httpx.AsyncClient, recipe_id: str) -> dict[str, Any]:
    return await ask(client, contracts.RECIPES_NUTRIENTS, {"id": recipe_id})


async def create_recipe(
    client: httpx.AsyncClient, name: str, ingredients: list[dict[str, Any]]
) -> dict[str, Any]:
    return await ask(
        client, contracts.RECIPES_CREATE, {"name": name, "servings": 1, "ingredients": ingredients}
    )
