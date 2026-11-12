from __future__ import annotations

from typing import Any

import httpx

from arga_tenancy import kernel_url, user_headers
from hub import catalogue
from hub.connections import Refused

TONES = range(1, 11)
TEXT_LIMIT = 60


async def inlets(transport: httpx.AsyncBaseTransport | None = None) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(
            base_url=kernel_url(), transport=transport, timeout=10.0
        ) as kernel:
            response = await kernel.get("/inlets", headers=user_headers())
            response.raise_for_status()
            found = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    if not isinstance(found, list):
        return []
    return [
        inlet
        for inlet in found
        if isinstance(inlet, dict) and {"key", "module", "contracts"} <= set(inlet)
    ]


def accepting(provider: catalogue.Provider, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    produced = set(provider.emits)
    return [inlet for inlet in found if produced & set(inlet["contracts"])]


def of_module(module: str, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [inlet for inlet in found if inlet["module"] == module]


def clean_settings(inlet: dict[str, Any], raw: dict[str, Any] | None, label: str) -> dict[str, Any]:
    raw = raw or {}
    out: dict[str, Any] = {}
    for setting in inlet.get("settings") or []:
        key, kind = setting["key"], setting["kind"]
        value = raw.get(key, setting.get("default"))
        if kind == "text":
            text = " ".join(str(value or label).split())[:TEXT_LIMIT]
            out[key] = text or label[:TEXT_LIMIT]
        elif kind == "tone":
            try:
                tone = int(value) if value is not None else None
            except (TypeError, ValueError):
                tone = None
            if tone is not None and tone not in TONES:
                raise Refused(f"{setting['label']}: un tono del 1 al {TONES[-1]}")
            if tone is not None:
                out[key] = tone
        elif kind == "choice":
            allowed = {choice["value"] for choice in setting.get("choices") or []}
            if value is not None and value not in allowed:
                raise Refused(f"{setting['label']}: elige una de {', '.join(sorted(allowed))}")
            if value is not None:
                out[key] = value
    return out


def plugs_for(
    provider: catalogue.Provider,
    found: list[dict[str, Any]],
    answers: dict[str, dict[str, Any]] | None,
    label: str,
) -> dict[str, dict[str, Any]]:
    answers = answers or {}
    return {
        inlet["key"]: clean_settings(inlet, answers.get(inlet["key"]), label)
        for inlet in accepting(provider, found)
    }


def described(provider: catalogue.Provider, found: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **catalogue.offer_of(provider),
        "inlets": [
            {
                "key": inlet["key"],
                "app": inlet["name"],
                "title": inlet["title"],
                "settings": inlet.get("settings") or [],
            }
            for inlet in accepting(provider, found)
        ],
    }


def groups() -> list[dict[str, str]]:
    return [{"id": group.id, "title": group.name} for group in catalogue.GROUPS]
