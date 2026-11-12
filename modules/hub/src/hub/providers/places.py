from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict, dataclass

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

SEARCH = "https://nominatim.openstreetmap.org/search"

MIN_INTERVAL = 1.1
CACHE_SECONDS = 24 * 3600
CACHE_SIZE = 500


def timeout() -> float:
    return float(os.environ.get("PLACES_SOURCE_TIMEOUT_SECONDS", "10"))


@dataclass(frozen=True)
class Candidate:
    name: str
    display_name: str
    lat: float
    lon: float
    osm_type: str
    osm_id: int
    kind: str
    country_code: str | None = None
    region_code: str | None = None
    town: str | None = None
    country: str | None = None


class SourceFailed(Exception):
    pass


class _Pace:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.last = 0.0
        self.cache: dict[tuple[str, int, str], tuple[float, list[Candidate]]] = {}

    def remembered(self, key: tuple[str, int, str]) -> list[Candidate] | None:
        found = self.cache.get(key)
        if found is None or time.monotonic() - found[0] > CACHE_SECONDS:
            return None
        return found[1]

    def remember(self, key: tuple[str, int, str], candidates: list[Candidate]) -> None:
        if len(self.cache) >= CACHE_SIZE:
            oldest = min(self.cache, key=lambda one: self.cache[one][0])
            del self.cache[oldest]
        self.cache[key] = (time.monotonic(), candidates)

    async def wait(self) -> None:
        pause = self.last + MIN_INTERVAL - time.monotonic()
        if pause > 0:
            await asyncio.sleep(pause)
        self.last = time.monotonic()


PACE = _Pace()


def _candidate(found: dict) -> Candidate | None:
    try:
        lat = float(found["lat"])
        lon = float(found["lon"])
        osm_id = int(found["osm_id"])
    except (KeyError, TypeError, ValueError):
        return None
    address = found.get("address") or {}
    display = str(found.get("display_name") or "").strip()
    name = str(found.get("name") or "").strip() or display.split(",")[0].strip()
    if not name:
        return None
    country = str(address.get("country_code") or "").strip().upper() or None
    region = address.get("ISO3166-2-lvl4") or address.get("ISO3166-2-lvl3")
    return Candidate(
        name=name,
        display_name=display or name,
        lat=lat,
        lon=lon,
        osm_type=str(found.get("osm_type") or "node"),
        osm_id=osm_id,
        kind=str(found.get("addresstype") or found.get("type") or "place"),
        country_code=country,
        region_code=str(region).upper() if region else None,
        town=_first(address, "city", "town", "village", "municipality"),
        country=_first(address, "country"),
    )


def _first(address: dict, *keys: str) -> str | None:
    for key in keys:
        value = str(address.get(key) or "").strip()
        if value:
            return value
    return None


async def search(
    client: httpx.AsyncClient, query: str, limit: int = 5, language: str = "es"
) -> list[Candidate]:
    key = (" ".join(query.lower().split()), limit, language)
    remembered = PACE.remembered(key)
    if remembered is not None:
        return remembered
    async with PACE.lock:
        remembered = PACE.remembered(key)
        if remembered is not None:
            return remembered
        await PACE.wait()
        try:
            response = await client.get(
                SEARCH,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": limit,
                    "accept-language": language,
                },
                headers={"user-agent": USER_AGENT},
                timeout=timeout(),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as error:
            raise SourceFailed(f"Nominatim no contestó: {type(error).__name__}") from error
        except ValueError as error:
            raise SourceFailed("Nominatim contestó algo que no es JSON") from error
    if not isinstance(payload, list):
        raise SourceFailed("Nominatim contestó algo que no es una lista de lugares")
    candidates = [one for one in (_candidate(found) for found in payload) if one is not None]
    PACE.remember(key, candidates)
    return candidates


def as_dict(candidate: Candidate) -> dict:
    return asdict(candidate)


SOURCES = (
    Provider(
        id="nominatim",
        name="OpenStreetMap",
        category="places",
        description="Los lugares de tus viajes por su nombre, con sus coordenadas, bajo demanda "
        "desde Travel o desde Claude. Sin clave: se conecta sola la primera vez que buscas.",
        capabilities=("lookup",),
        serves=("places.search",),
        available=True,
        single=True,
    ),
)
