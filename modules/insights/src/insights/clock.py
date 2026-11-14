from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from arga_contracts import notify
from arga_module import preferences
from arga_tenancy import kernel_url, user_headers


def zone() -> ZoneInfo:
    person = preferences.current()
    return person.zone if person != preferences.defaults() else notify.zone()


def now() -> datetime:
    return datetime.now(zone())


def today() -> date:
    return now().date()


async def of_person(client: httpx.AsyncClient) -> preferences.Preferences:
    try:
        response = await client.get(
            f"{kernel_url()}/me/preferences", headers=user_headers(), timeout=10.0
        )
        response.raise_for_status()
        given = response.json()
        return preferences.from_headers(
            {
                header: str(given[field])
                for field, header in preferences.HEADERS.items()
                if given.get(field)
            }
        )
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return preferences.defaults()
