from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import Literal

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

INTERPRETER = "https://overpass-api.de/api/interpreter"
RETRY_SECONDS = 2.0

MIN_INTERVAL = 1.0
CACHE_SECONDS = 24 * 3600
CACHE_SIZE = 300

Kind = Literal["food", "sights", "nature", "shopping", "nightlife"]

FILTERS: dict[str, tuple[str, ...]] = {
    "food": ('["amenity"~"^(restaurant|cafe|fast_food|ice_cream|food_court)$"]',),
    "sights": (
        '["tourism"~"^(attraction|museum|gallery|viewpoint|artwork|zoo|aquarium|theme_park)$"]',
        '["historic"~"^(monument|castle|ruins|memorial|archaeological_site|church|fort)$"]',
        '["amenity"="place_of_worship"]["wikidata"]',
    ),
    "nature": (
        '["leisure"~"^(park|garden|nature_reserve)$"]',
        '["natural"~"^(beach|peak|waterfall|cave_entrance)$"]',
    ),
    "shopping": (
        '["shop"~"^(mall|department_store|books|gift|art|crafts)$"]',
        '["amenity"="marketplace"]',
    ),
    "nightlife": ('["amenity"~"^(bar|pub|nightclub|biergarten)$"]',),
}


def timeout() -> float:
    return float(os.environ.get("NEARBY_SOURCE_TIMEOUT_SECONDS", "25"))


class SourceFailed(Exception):
    pass


@dataclass(frozen=True)
class Nearby:
    name: str
    lat: float
    lon: float
    osm_type: str
    osm_id: int
    kind: str
    group: str
    distance_m: int
    cuisine: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    wikidata: str | None = None
    local_name: str | None = None


class _Pace:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.last = 0.0
        self.cache: dict[tuple, tuple[float, list[Nearby]]] = {}


PACE = _Pace()


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)))


def query(kind: str, lat: float, lon: float, radius: int, limit: int) -> str:
    around = f"(around:{radius},{lat:.6f},{lon:.6f})"
    parts = "".join(f'nwr{one}["name"]{around};' for one in FILTERS[kind])
    return f"[out:json][timeout:20];({parts});out center tags {limit * 3};"


def _nearby(found: dict, group: str, lat: float, lon: float) -> Nearby | None:
    tags = found.get("tags") or {}
    name = str(tags.get("name:es") or tags.get("name:en") or tags.get("name") or "").strip()
    point = found.get("center") or found
    try:
        there_lat, there_lon = float(point["lat"]), float(point["lon"])
        osm_id = int(found["id"])
    except (KeyError, TypeError, ValueError):
        return None
    if not name:
        return None
    kind = next(
        (
            str(tags[key])
            for key in ("tourism", "historic", "amenity", "leisure", "natural", "shop")
            if tags.get(key)
        ),
        "place",
    )
    return Nearby(
        name=name,
        lat=there_lat,
        lon=there_lon,
        osm_type=str(found.get("type") or "node"),
        osm_id=osm_id,
        kind=kind,
        group=group,
        distance_m=metres(lat, lon, there_lat, there_lon),
        cuisine=tags.get("cuisine"),
        website=tags.get("website") or tags.get("contact:website"),
        opening_hours=tags.get("opening_hours"),
        wikidata=tags.get("wikidata"),
        local_name=tags.get("name") if tags.get("name") and tags.get("name") != name else None,
    )


async def _ask(client: httpx.AsyncClient, sent: str) -> dict:
    problem = "Overpass did not answer"
    for attempt in range(2):
        if attempt:
            await asyncio.sleep(RETRY_SECONDS)
        try:
            response = await client.post(
                INTERPRETER,
                data={"data": sent},
                headers={"user-agent": USER_AGENT},
                timeout=timeout(),
            )
        except httpx.HTTPError as error:
            problem = f"Overpass did not answer: {type(error).__name__}"
            continue
        if response.status_code in (429, 502, 503, 504):
            problem = "Overpass is overloaded: too many queries right now"
            continue
        if response.status_code != 200:
            raise SourceFailed(f"Overpass answered {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise SourceFailed("Overpass answered something that is not JSON") from error
    raise SourceFailed(problem)


async def around(
    client: httpx.AsyncClient, kind: Kind, lat: float, lon: float, radius: int, limit: int
) -> list[Nearby]:
    key = (kind, round(lat, 4), round(lon, 4), radius, limit)
    found = PACE.cache.get(key)
    if found and time.monotonic() - found[0] < CACHE_SECONDS:
        return found[1]
    async with PACE.lock:
        pause = PACE.last + MIN_INTERVAL - time.monotonic()
        if pause > 0:
            await asyncio.sleep(pause)
        PACE.last = time.monotonic()
        payload = await _ask(client, query(kind, lat, lon, radius, limit))
    elements = payload.get("elements") if isinstance(payload, dict) else None
    if not isinstance(elements, list):
        raise SourceFailed("Overpass answered something that is not a list of places")
    seen: set[str] = set()
    places: list[Nearby] = []
    for one in sorted(
        (item for item in (_nearby(e, kind, lat, lon) for e in elements) if item is not None),
        key=lambda item: item.distance_m,
    ):
        if one.name.lower() in seen:
            continue
        seen.add(one.name.lower())
        places.append(one)
    places = places[:limit]
    if len(PACE.cache) >= CACHE_SIZE:
        del PACE.cache[min(PACE.cache, key=lambda one: PACE.cache[one][0])]
    PACE.cache[key] = (time.monotonic(), places)
    return places


def as_dict(one: Nearby) -> dict:
    return asdict(one)


SOURCES = (
    Provider(
        id="overpass",
        name="Nearby places",
        category="places",
        description="Restaurants, museums, parks and everything else near a "
        "place, from OpenStreetMap, for a trip in Travel or from an "
        "AI assistant. No key: it connects by itself.",
        capabilities=("lookup",),
        serves=("places.nearby",),
        available=True,
        single=True,
    ),
)
