from __future__ import annotations

import math
import re
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT = "Europe/Madrid"
TABLE = Path("/usr/share/zoneinfo/zone.tab")

_COORDS = re.compile(r"^([+-]\d{4,6})([+-]\d{5,7})$")


def _degrees(value: str, width: int) -> float:
    sign = -1 if value[0] == "-" else 1
    digits = value[1:]
    whole = int(digits[:width])
    minutes = int(digits[width : width + 2])
    seconds = int(digits[width + 2 : width + 4] or 0)
    return sign * (whole + minutes / 60 + seconds / 3600)


@cache
def _zones() -> tuple[tuple[str, float, float, str], ...]:
    try:
        lines = TABLE.read_text(encoding="ascii").splitlines()
    except OSError:
        return ()
    rows = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 3:
            continue
        found = _COORDS.match(fields[1])
        if not found:
            continue
        try:
            ZoneInfo(fields[2])
        except (ZoneInfoNotFoundError, ValueError):
            continue
        rows.append(
            (fields[0], _degrees(found.group(1), 2), _degrees(found.group(2), 3), fields[2])
        )
    return tuple(rows)


def _distance(lat: float, lon: float, other_lat: float, other_lon: float) -> float:
    a, b = math.radians(lat), math.radians(other_lat)
    d_lat, d_lon = b - a, math.radians(other_lon - lon)
    return math.asin(
        math.sqrt(math.sin(d_lat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(d_lon / 2) ** 2)
    )


def zone_of(country_code: str | None, lat: float | None, lon: float | None) -> str:
    rows = _zones()
    country = (country_code or "").upper()
    candidates = [row for row in rows if row[0] == country] if country else []
    if lat is None or lon is None:
        return candidates[0][3] if len(candidates) == 1 else DEFAULT
    candidates = candidates or list(rows)
    if not candidates:
        return DEFAULT
    return min(candidates, key=lambda row: _distance(lat, lon, row[1], row[2]))[3]
