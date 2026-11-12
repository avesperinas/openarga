from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

NEAR_DEGREES = 0.25
EARTH_KM = 6371.0088

Ring = list[tuple[float, float]]


def geo_dir() -> Path:
    default = Path(__file__).resolve().parents[4] / "packages" / "ui" / "geo"
    return Path(os.environ.get("GEO_DIR", default))


@dataclass(frozen=True)
class Area:
    code: str
    name: str
    country: str | None
    polygons: tuple[tuple[Ring, ...], ...]
    bbox: tuple[float, float, float, float]

    def contains(self, lon: float, lat: float) -> bool:
        west, south, east, north = self.bbox
        if not (west <= lon <= east and south <= lat <= north):
            return False
        return any(_inside(rings, lon, lat) for rings in self.polygons)

    def distance(self, lon: float, lat: float) -> float:
        return min(
            _segment_distance(lon, lat, ring[i], ring[i + 1])
            for rings in self.polygons
            for ring in rings
            for i in range(len(ring) - 1)
        )


def _extent(bbox: tuple[float, float, float, float]) -> float:
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def _inside(rings: tuple[Ring, ...], lon: float, lat: float) -> bool:
    inside = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _segment_distance(px: float, py: float, a: tuple[float, float], b: tuple[float, float]):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _decode(topology: dict, name: str) -> list[Area]:
    scale_x, scale_y = topology["transform"]["scale"]
    shift_x, shift_y = topology["transform"]["translate"]
    arcs: list[Ring] = []
    for arc in topology["arcs"]:
        x = y = 0
        points: Ring = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * scale_x + shift_x, y * scale_y + shift_y))
        arcs.append(points)

    def ring(indexes: list[int]) -> Ring:
        points: Ring = []
        for index in indexes:
            arc = arcs[index] if index >= 0 else arcs[~index][::-1]
            points.extend(arc if not points else arc[1:])
        return points

    areas = []
    for geometry in topology["objects"][name]["geometries"]:
        kind = geometry.get("type")
        if kind == "Polygon":
            polygons = [geometry["arcs"]]
        elif kind == "MultiPolygon":
            polygons = geometry["arcs"]
        else:
            continue
        shapes = tuple(tuple(ring(r) for r in polygon) for polygon in polygons)
        xs = [x for rings in shapes for r in rings for x, _ in r]
        ys = [y for rings in shapes for r in rings for _, y in r]
        properties = geometry.get("properties") or {}
        areas.append(
            Area(
                code=str(properties["code"]),
                name=str(properties.get("name") or properties["code"]),
                country=properties.get("country"),
                polygons=shapes,
                bbox=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    return areas


@cache
def countries() -> tuple[Area, ...]:
    return tuple(_decode(json.loads((geo_dir() / "countries.json").read_text()), "countries"))


@cache
def regions() -> tuple[Area, ...]:
    return tuple(_decode(json.loads((geo_dir() / "regions.json").read_text()), "regions"))


@cache
def names() -> dict[str, str]:
    return {area.code: area.name for area in (*countries(), *regions())}


def _find(areas: tuple[Area, ...], lon: float, lat: float) -> Area | None:
    inside = [area for area in areas if area.contains(lon, lat)]
    if inside:
        return min(inside, key=lambda area: _extent(area.bbox))
    near = [
        area
        for area in areas
        if area.bbox[0] - NEAR_DEGREES <= lon <= area.bbox[2] + NEAR_DEGREES
        and area.bbox[1] - NEAR_DEGREES <= lat <= area.bbox[3] + NEAR_DEGREES
    ]
    best = min(near, key=lambda area: area.distance(lon, lat), default=None)
    if best is not None and best.distance(lon, lat) <= NEAR_DEGREES:
        return best
    return None


def locate(
    lat: float | None,
    lon: float | None,
    hint_country: str | None = None,
    hint_region: str | None = None,
) -> tuple[str | None, str | None]:
    known = names()
    country = region = None
    if lat is not None and lon is not None:
        found_country = _find(countries(), lon, lat)
        country = found_country.code if found_country else None
        candidates = tuple(area for area in regions() if country is None or area.country == country)
        found_region = _find(candidates, lon, lat)
        region = found_region.code if found_region else None
        if country is None and found_region is not None:
            country = found_region.country
    if country is None and hint_country and hint_country.upper() in known:
        country = hint_country.upper()
    if region is None and hint_region and hint_region.upper() in known:
        hinted = hint_region.upper()
        if country is None or hinted.startswith(f"{country}-"):
            region = hinted
    return country, region


EUROPE = frozenset(
    {
        *("AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CZ", "DK", "EE", "FI", "FR", "DE"),
        *("GR", "VA", "HU", "IS", "IE", "IT", "LV", "LI", "LT", "LU", "MT", "MD", "MC", "ME"),
        *("NL", "MK", "NO", "PL", "PT", "RO", "RU", "SM", "RS", "SK", "SI", "ES", "SE", "CH"),
        *("UA", "GB"),
    }
)

DETOUR = {"plane": 1.0, "train": 1.2, "car": 1.25, "bus": 1.25, "boat": 1.15}


def great_circle_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def leg_km(
    mode: str, start: tuple[float | None, float | None], end: tuple[float | None, float | None]
) -> float | None:
    if None in start or None in end:
        return None
    return round(great_circle_km(start, end) * DETOUR[mode], 1)  # type: ignore[arg-type]
