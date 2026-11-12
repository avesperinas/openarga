from __future__ import annotations

from typing import Any

import httpx

from arga_tenancy import kernel_url, user_headers
from hub import catalogue, plugs

MODULE = "hub"


async def modules(transport: httpx.AsyncBaseTransport | None = None) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(
            base_url=kernel_url(), transport=transport, timeout=10.0
        ) as kernel:
            response = await kernel.get("/modules", headers=user_headers())
            response.raise_for_status()
            found = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    if not isinstance(found, list):
        return []
    return [one for one in found if isinstance(one, dict) and one.get("enabled") and "id" in one]


def serving(capability: str) -> list[str]:
    return [one.id for one in catalogue.PROVIDERS if capability in one.serves]


def by_app(
    installed: list[dict[str, Any]], inlets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    apps: list[dict[str, Any]] = []
    reached: set[str] = set()
    for module in sorted(installed, key=lambda one: str(one.get("name") or one["id"])):
        if module["id"] == MODULE:
            continue
        own = [
            {
                "key": inlet["key"],
                "title": inlet["title"],
                "settings": inlet.get("settings") or [],
                "providers": [
                    one.id
                    for one in catalogue.PROVIDERS
                    if set(one.emits) & set(inlet["contracts"])
                ],
            }
            for inlet in plugs.of_module(module["id"], inlets)
        ]
        own = [inlet for inlet in own if inlet["providers"]]
        asked: dict[str, list[str]] = {}
        for capability in module.get("uses") or []:
            for provider in serving(capability):
                asked.setdefault(provider, []).append(capability)
        services = [
            {"provider": provider, "capabilities": caps} for provider, caps in asked.items()
        ]
        if not own and not services:
            continue
        reached |= {provider for inlet in own for provider in inlet["providers"]} | set(asked)
        apps.append(
            {
                "module": module["id"],
                "name": module.get("name") or module["id"],
                "view": module.get("view"),
                "inlets": own,
                "services": services,
            }
        )
    others = [one.id for one in catalogue.PROVIDERS if one.id not in reached]
    return apps, others
