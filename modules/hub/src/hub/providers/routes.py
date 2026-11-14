from __future__ import annotations

import os
import time
from typing import Literal

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

Profile = Literal["foot", "bike", "car"]
ROUTE = "https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/{points}"

CACHE_SECONDS = 24 * 3600
CACHE_SIZE = 300


def timeout() -> float:
    return float(os.environ.get("ROUTES_SOURCE_TIMEOUT_SECONDS", "15"))


class SourceFailed(Exception):
    pass


CACHE: dict[tuple, tuple[float, dict]] = {}


async def directions(
    client: httpx.AsyncClient, profile: Profile, points: list[tuple[float, float]]
) -> dict:
    key = (profile, tuple((round(lon, 6), round(lat, 6)) for lon, lat in points))
    found = CACHE.get(key)
    if found and time.monotonic() - found[0] < CACHE_SECONDS:
        return found[1]
    url = ROUTE.format(
        profile=profile, points=";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)
    )
    try:
        response = await client.get(
            url,
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            headers={"user-agent": USER_AGENT},
            timeout=timeout(),
        )
        payload = response.json()
    except httpx.HTTPError as error:
        raise SourceFailed(f"OSRM did not answer: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("OSRM answered something that is not JSON") from error
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise SourceFailed(f"OSRM found no route: {payload.get('code') or response.status_code}")
    route = payload["routes"][0]
    answer = {
        "distance_m": round(float(route["distance"])),
        "duration_s": round(float(route["duration"])),
        "legs": [
            {
                "distance_m": round(float(leg["distance"])),
                "duration_s": round(float(leg["duration"])),
            }
            for leg in route.get("legs", [])
        ],
        "geometry": route["geometry"]["coordinates"],
    }
    if len(CACHE) >= CACHE_SIZE:
        del CACHE[min(CACHE, key=lambda one: CACHE[one][0])]
    CACHE[key] = (time.monotonic(), answer)
    return answer


SOURCES = (
    Provider(
        id="osrm",
        name="OpenStreetMap routes",
        category="places",
        description="How to get from one place to another on foot, by bike or by "
        "car, with its distance and time, for the map of each day of "
        "a trip in Travel. No key: it connects by itself.",
        capabilities=("lookup",),
        serves=("routes.directions",),
        available=True,
        single=True,
    ),
)
