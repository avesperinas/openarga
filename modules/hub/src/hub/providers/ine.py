from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from hub.declare import Provider, Sync
from hub.providers import SourceError

PROVIDER = "ine"
CPI = "economy.cpi"
SERIES = "IPC251852"
BASE_YEAR = 2021
MONTHS = 120


def base_url() -> str:
    return os.environ.get("INE_URL", "https://servicios.ine.es/wstempus/js/ES").rstrip("/")


def points(body: dict[str, Any]) -> list[tuple[str, float]]:
    found = []
    for item in body.get("Data") or []:
        year, month, value = item.get("Anyo"), item.get("FK_Periodo"), item.get("Valor")
        if not isinstance(year, int) or not isinstance(month, int) or not 1 <= month <= 12:
            continue
        if not isinstance(value, (int, float)) or item.get("Secreto"):
            continue
        found.append((f"{year:04d}-{month:02d}", float(value)))
    return sorted(found)


def events(found: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [
        {
            "ts": datetime.fromisoformat(f"{month}-01T00:00:00").replace(tzinfo=UTC).isoformat(),
            "type": CPI,
            "payload": {
                "month": month,
                "index": value,
                "series": SERIES,
                "base_year": BASE_YEAR,
                "area": "ES",
            },
            "dedup_hash": f"{PROVIDER}:{SERIES}:{month}:{value:.3f}",
        }
        for month, value in found
    ]


async def fetch(client: httpx.AsyncClient) -> list[tuple[str, float]]:
    try:
        response = await client.get(
            f"{base_url()}/DATOS_SERIE/{SERIES}", params={"nult": MONTHS}, timeout=30.0
        )
    except httpx.HTTPError as error:
        raise SourceError(
            f"INE is not answering ({type(error).__name__})", transient=True
        ) from error
    if response.status_code == 429:
        raise SourceError("INE asks to wait", rate_limited=True)
    if response.status_code >= 500:
        raise SourceError(f"INE fails ({response.status_code})", transient=True)
    if response.status_code >= 400:
        raise SourceError(f"INE answers {response.status_code}")
    try:
        body = response.json()
    except ValueError as error:
        raise SourceError("INE does not answer with data") from error
    found = points(body if isinstance(body, dict) else {})
    if not found:
        raise SourceError(f"INE gives no month of series {SERIES}")
    return found


async def sync(client: httpx.AsyncClient, _secrets: dict[str, str], _connection: Any) -> list[dict]:
    return events(await fetch(client))


SOURCES = (
    Provider(
        id="ine",
        name="INE",
        category="economy",
        description="The INE consumer price index, month by month: the national general "
        "index, which Career uses to show your salary in today's euros. Public and keyless; "
        "fetched once a day.",
        capabilities=("sync",),
        emits=("economy.cpi",),
        available=True,
        single=True,
        schedule="10 6 * * *",
        sync=Sync("cpi", sync),
    ),
)
