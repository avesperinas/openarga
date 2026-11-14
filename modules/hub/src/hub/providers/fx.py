from __future__ import annotations

import os
import time
from datetime import date

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

RATES = "https://api.frankfurter.dev/v1/{day}"

PAST_SECONDS = 7 * 24 * 3600
TODAY_SECONDS = 3600
CACHE_SIZE = 500


def timeout() -> float:
    return float(os.environ.get("FX_SOURCE_TIMEOUT_SECONDS", "15"))


class SourceFailed(Exception):
    pass


CACHE: dict[tuple[str, str], tuple[float, dict]] = {}


async def rate(client: httpx.AsyncClient, currency: str, day: date, today: date) -> dict:
    currency = currency.upper()
    if currency == "EUR":
        return {"currency": "EUR", "rate": 1.0, "date": day.isoformat()}
    asked = min(day, today)
    key = (currency, asked.isoformat())
    found = CACHE.get(key)
    keep = TODAY_SECONDS if asked >= today else PAST_SECONDS
    if found and time.monotonic() - found[0] < keep:
        return found[1]
    try:
        response = await client.get(
            RATES.format(day=asked.isoformat()),
            params={"base": currency, "symbols": "EUR"},
            headers={"user-agent": USER_AGENT},
            timeout=timeout(),
            follow_redirects=True,
        )
        payload = response.json()
    except httpx.HTTPError as error:
        raise SourceFailed(f"Frankfurter no contestó: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("Frankfurter contestó algo que no es JSON") from error
    if response.status_code == 404 or (response.status_code == 422):
        raise SourceFailed(f"el BCE no publica el cambio de {currency}")
    value = (payload.get("rates") or {}).get("EUR") if isinstance(payload, dict) else None
    if response.status_code != 200 or value is None:
        raise SourceFailed(f"Frankfurter no dio el cambio de {currency}")
    answer = {"currency": currency, "rate": float(value), "date": payload.get("date")}
    if len(CACHE) >= CACHE_SIZE:
        del CACHE[min(CACHE, key=lambda one: CACHE[one][0])]
    CACHE[key] = (time.monotonic(), answer)
    return answer


SOURCES = (
    Provider(
        id="frankfurter",
        name="Exchange rates (ECB)",
        category="finance",
        description="The euro exchange rate of a day, from the European Central "
        "Bank, for trip expenses in another currency in Travel or "
        "from an AI assistant. No key: it connects by itself.",
        capabilities=("lookup",),
        serves=("fx.rate",),
        available=True,
        single=True,
    ),
)
