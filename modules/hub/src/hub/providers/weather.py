from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import date

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

FORECAST_SECONDS = 3600
CLIMATE_SECONDS = 30 * 24 * 3600
YEARS = 10
CACHE_SIZE = 300

SKY: dict[int, str] = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "showers",
    81: "showers",
    82: "heavy showers",
    85: "snow showers",
    86: "snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


def timeout() -> float:
    return float(os.environ.get("WEATHER_SOURCE_TIMEOUT_SECONDS", "20"))


class SourceFailed(Exception):
    pass


CACHE: dict[tuple, tuple[float, dict]] = {}


def _remembered(key: tuple, seconds: int) -> dict | None:
    found = CACHE.get(key)
    if found and time.monotonic() - found[0] < seconds:
        return found[1]
    return None


def _remember(key: tuple, value: dict) -> dict:
    if len(CACHE) >= CACHE_SIZE:
        del CACHE[min(CACHE, key=lambda one: CACHE[one][0])]
    CACHE[key] = (time.monotonic(), value)
    return value


async def _get(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    try:
        response = await client.get(
            url, params=params, headers={"user-agent": USER_AGENT}, timeout=timeout()
        )
        payload = response.json()
    except httpx.HTTPError as error:
        raise SourceFailed(f"Open-Meteo did not answer: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("Open-Meteo answered something that is not JSON") from error
    if response.status_code != 200 or payload.get("error"):
        raise SourceFailed(f"Open-Meteo refused: {payload.get('reason') or response.status_code}")
    return payload


def _round(value) -> float | None:
    return round(float(value), 1) if value is not None else None


async def forecast(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    key = ("forecast", round(lat, 2), round(lon, 2))
    remembered = _remembered(key, FORECAST_SECONDS)
    if remembered is not None:
        return remembered
    payload = await _get(
        client,
        FORECAST,
        {
            "latitude": lat,
            "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 16,
        },
    )
    daily = payload.get("daily") or {}
    days = []
    for index, day in enumerate(daily.get("time", [])):
        code = daily.get("weather_code", [None] * (index + 1))[index]
        sky = SKY.get(int(code), "") if code is not None else ""
        days.append(
            {
                "day": day,
                "code": code,
                "sky": sky,
                "max_c": _round(daily.get("temperature_2m_max", [None] * (index + 1))[index]),
                "min_c": _round(daily.get("temperature_2m_min", [None] * (index + 1))[index]),
                "rain_chance": daily.get("precipitation_probability_max", [None] * (index + 1))[
                    index
                ],
            }
        )
    return _remember(key, {"timezone": payload.get("timezone"), "days": days})


async def climate(client: httpx.AsyncClient, lat: float, lon: float, today: date) -> dict:
    key = ("climate", round(lat, 1), round(lon, 1))
    remembered = _remembered(key, CLIMATE_SECONDS)
    if remembered is not None:
        return remembered
    last = today.year - 1
    payload = await _get(
        client,
        ARCHIVE,
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": f"{last - YEARS + 1}-01-01",
            "end_date": f"{last}-12-31",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        },
    )
    daily = payload.get("daily") or {}
    highs, lows, rain = defaultdict(list), defaultdict(list), defaultdict(float)
    rainy = defaultdict(int)
    for index, day in enumerate(daily.get("time", [])):
        month = int(day[5:7])
        high = daily.get("temperature_2m_max", [])[index]
        low = daily.get("temperature_2m_min", [])[index]
        wet = daily.get("precipitation_sum", [])[index]
        if high is not None:
            highs[month].append(high)
        if low is not None:
            lows[month].append(low)
        if wet is not None:
            rain[month] += wet
            rainy[month] += 1 if wet >= 1 else 0
    if not highs:
        raise SourceFailed("Open-Meteo has no climate for that place")
    months = [
        {
            "month": month,
            "max_c": round(sum(highs[month]) / len(highs[month]), 1),
            "min_c": round(sum(lows[month]) / len(lows[month]), 1) if lows[month] else None,
            "rain_mm": round(rain[month] / YEARS),
            "rain_days": round(rainy[month] / YEARS, 1),
        }
        for month in range(1, 13)
        if highs[month]
    ]
    return _remember(
        key,
        {
            "timezone": payload.get("timezone"),
            "years": f"{last - YEARS + 1}–{last}",
            "months": months,
        },
    )


SOURCES = (
    Provider(
        id="open_meteo",
        name="Open-Meteo",
        category="weather",
        description="The weather at the places of your trips: the forecast for "
        "the next days and the climate of each month, for Travel and "
        "for an AI assistant. No key: it connects by itself.",
        capabilities=("lookup",),
        serves=("weather.forecast", "weather.climate"),
        available=True,
        single=True,
    ),
)
