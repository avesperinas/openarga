from __future__ import annotations

import os
from typing import Any

import httpx

from arga_module.hub import ask
from travel import geo, travel

MODULE = "travel"


def timeout() -> float:
    return float(os.environ.get("PLACES_SEARCH_TIMEOUT_SECONDS", "30"))


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def search(query: str, limit: int = 5) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await ask(
                client, MODULE, "places.search", {"query": query, "limit": limit}, timeout()
            )
        if response.status_code == 200:
            answer = response.json()
        else:
            answer = {
                "candidates": [],
                "failed": [
                    {"source": "nominatim", "reason": f"Hub contesta {response.status_code}"}
                ],
            }
    except httpx.HTTPError as error:
        answer = {
            "candidates": [],
            "failed": [
                {
                    "source": "nominatim",
                    "reason": f"Hub no contesta ({type(error).__name__})",
                }
            ],
        }
    known = geo.names()
    for candidate in answer.get("candidates", []):
        country, region = geo.locate(
            candidate.get("lat"),
            candidate.get("lon"),
            candidate.get("country_code"),
            candidate.get("region_code"),
        )
        candidate["country_code"], candidate["region_code"] = country, region
        candidate["country"] = known.get(country) if country else None
        candidate["region"] = known.get(region) if region else None
    return answer


async def _ask(capability: str, body: dict[str, Any], seconds: float) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await ask(client, MODULE, capability, body, seconds)
    except httpx.HTTPError as error:
        return {"failed": f"Hub no contesta ({type(error).__name__})"}
    if response.status_code != 200:
        return {"failed": f"Hub contesta {response.status_code}"}
    return response.json()


async def tile(z: int, x: int, y: int) -> dict[str, Any]:
    return await _ask("maps.tile", {"z": z, "x": x, "y": y}, 20.0)


async def directions(profile: str, points: list[tuple[float, float]]) -> dict[str, Any]:
    return await _ask("routes.directions", {"profile": profile, "points": points}, 20.0)


async def nearby(lat: float, lon: float, kind: str, radius: int, limit: int) -> dict[str, Any]:
    answer = await _ask(
        "places.nearby",
        {"lat": lat, "lon": lon, "kind": kind, "radius": radius, "limit": limit},
        40.0,
    )
    known = geo.names()
    for candidate in answer.get("places", []):
        country, region = geo.locate(candidate.get("lat"), candidate.get("lon"), None, None)
        candidate["country_code"], candidate["region_code"] = country, region
        candidate["country"] = known.get(country) if country else None
        candidate["region"] = known.get(region) if region else None
        candidate["display_name"] = candidate.get("local_name") or candidate["name"]
        candidate["category"] = travel.category_of(candidate.get("kind")) or NEARBY_CATEGORY.get(
            kind
        )
    return {"places": answer.get("places", []), "failed": answer.get("failed")}


NEARBY_CATEGORY = {
    "sights": "culture",
    "food": "restaurant",
    "nature": "nature",
    "shopping": "shopping",
    "nightlife": "nightlife",
}


async def place_photo(body: dict[str, Any]) -> dict[str, Any]:
    return await _ask(
        "places.photo", body, float(os.environ.get("PLACE_PHOTO_TIMEOUT_SECONDS", "60"))
    )


async def forecast(lat: float, lon: float) -> dict[str, Any]:
    return await _ask("weather.forecast", {"lat": lat, "lon": lon}, 30.0)


async def climate(lat: float, lon: float) -> dict[str, Any]:
    return await _ask("weather.climate", {"lat": lat, "lon": lon}, 40.0)


async def fx(currency: str, day: str | None) -> dict[str, Any]:
    return await _ask("fx.rate", {"currency": currency, "day": day}, 20.0)
