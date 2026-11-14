from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from hub.declare import Ask, Offer, Provider, Setting, Sync
from hub.providers import SourceError
from hub.providers.calendars import Item, events, window

PROVIDER = "holidays"
HOLIDAYS = "calendar.holidays"
BASE = "https://date.nager.at/api/v3"
COUNTRY = "country"
REGION = "region"

REGIONS: dict[str, dict[str, str]] = {
    "ES": {
        "ES-AN": "Andalucía",
        "ES-AR": "Aragón",
        "ES-AS": "Asturias",
        "ES-CB": "Cantabria",
        "ES-CE": "Ceuta",
        "ES-CL": "Castilla y León",
        "ES-CM": "Castilla-La Mancha",
        "ES-CN": "Canarias",
        "ES-CT": "Cataluña",
        "ES-EX": "Extremadura",
        "ES-GA": "Galicia",
        "ES-IB": "Illes Balears",
        "ES-MC": "Región de Murcia",
        "ES-MD": "Comunidad de Madrid",
        "ES-ML": "Melilla",
        "ES-NC": "Navarra",
        "ES-PV": "País Vasco",
        "ES-RI": "La Rioja",
        "ES-VC": "Comunitat Valenciana",
    }
}


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    country = str(raw.get(COUNTRY) or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("el país va con su código de dos letras, como ES")
    region = str(raw.get(REGION) or "").strip().upper() or None
    if region is not None and not re.fullmatch(rf"{country}-[A-Z0-9]{{1,3}}", region):
        raise ValueError(f"la región va con su código, como {country}-NC")
    return {COUNTRY: country, REGION: region}


def region_name(country: str, region: str) -> str:
    return REGIONS.get(country, {}).get(region, region)


async def _get(client: httpx.AsyncClient, path: str) -> Any:
    try:
        response = await client.get(f"{BASE}{path}", timeout=20.0)
    except httpx.HTTPError as error:
        raise SourceError(
            f"Nager.Date no contesta ({type(error).__name__})", transient=True
        ) from error
    if response.status_code == 429:
        raise SourceError("Nager.Date pide esperar", rate_limited=True)
    if response.status_code >= 500:
        raise SourceError(f"Nager.Date falla ({response.status_code})", transient=True)
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise SourceError(f"Nager.Date contesta {response.status_code}")
    if response.status_code == 204 or not response.content:
        return []
    return response.json()


def items_of(found: list[dict[str, Any]], country: str, region: str | None) -> list[Item]:
    items: list[Item] = []
    for holiday in found:
        if "Public" not in (holiday.get("types") or ["Public"]):
            continue
        counties = holiday.get("counties") or []
        if not holiday.get("global", True) and (region is None or region not in counties):
            continue
        day = date.fromisoformat(holiday["date"])
        title = holiday.get("localName") or holiday.get("name") or "Festivo"
        items.append(
            Item(
                uid=f"{country}:{day.isoformat()}:{holiday.get('name') or title}",
                title=title,
                all_day=True,
                start=day.isoformat(),
                end=(day + timedelta(days=1)).isoformat(),
                description=None
                if holiday.get("global", True)
                else f"Festivo en {', '.join(region_name(country, c) for c in counties)}",
            )
        )
    return items


async def fetch(
    client: httpx.AsyncClient, country: str, region: str | None, today: date
) -> list[Item]:
    first, last = window(today)
    items: list[Item] = []
    for year in range(first.year, last.year + 1):
        found = await _get(client, f"/PublicHolidays/{year}/{country}")
        if found is None:
            if year == today.year:
                raise SourceError(f"Nager.Date no tiene los festivos de {country}")
            continue
        items.extend(items_of(found, country, region))
    return items


def listed(connection: Any, items: list[Item], now: datetime) -> dict[str, Any]:
    config = connection.config or {}
    first, last = window(now.date())
    days: dict[str, list[str]] = {}
    for item in items:
        if first.isoformat() <= item.start <= last.isoformat():
            days.setdefault(item.start, []).append(item.title)
    return {
        "ts": now.isoformat(),
        "type": HOLIDAYS,
        "payload": {
            "connection": str(connection.id),
            "country": config.get(COUNTRY) or "",
            "region": config.get(REGION),
            "from": first.isoformat(),
            "to": last.isoformat(),
            "days": {day: " · ".join(names) for day, names in sorted(days.items())},
        },
        "dedup_hash": f"holidays:{connection.id}:{now.isoformat()}",
    }


async def sync(client: httpx.AsyncClient, _secrets: dict[str, str], connection: Any) -> list[dict]:
    config = connection.config or {}
    now = datetime.now(UTC)
    items = await fetch(client, config.get(COUNTRY) or "", config.get(REGION), now.date())
    found = events(connection, connection.provider, items, now)
    return [*found[:-1], listed(connection, items, now), found[-1]]


async def countries(client: httpx.AsyncClient) -> list[dict[str, str]]:
    found = await _get(client, "/AvailableCountries") or []
    return [{"code": item["countryCode"], "name": item["name"]} for item in found]


async def regions(client: httpx.AsyncClient, country: str, today: date) -> list[dict[str, str]]:
    found = await _get(client, f"/PublicHolidays/{today.year}/{country}") or []
    codes = sorted({code for item in found for code in (item.get("counties") or [])})
    named = [{"code": code, "name": region_name(country, code)} for code in codes]
    return sorted(named, key=lambda item: item["name"])


async def search_countries(
    client: httpx.AsyncClient, _query: str | None, _parent: str | None
) -> list[dict[str, str]]:
    return await countries(client)


async def search_regions(
    client: httpx.AsyncClient, _query: str | None, parent: str | None
) -> list[dict[str, str]]:
    if not parent or len(parent) != 2:
        raise ValueError("falta el país")
    return await regions(client, parent.upper(), datetime.now(UTC).date())


SOURCES = (
    Provider(
        id="holidays",
        name="Public holidays",
        category="calendar",
        description="The public holidays of a country and, if you want, of your "
        "region, from Nager.Date. Your city's are in no source: add "
        "them with a .ics calendar if there is one. Subscribed from "
        "Planner.",
        capabilities=("sync",),
        settings=(
            Setting("country", "Country", "Its two-letter code: ES, FR, PT…", "ES"),
            Setting(
                "region",
                "Region",
                "Its ISO code, like ES-NC for Navarre. Empty, only the national ones.",
            ),
        ),
        emits=("calendar.event", "calendar.feed", HOLIDAYS),
        available=True,
        schedule="30 3 * * 1",
        offer=Offer(
            title="Public holidays",
            subtitle="Your country's and your region's",
            tone=4,
            many=True,
            group="holidays",
            name="Holidays · {region|country}",
            asks=(
                Ask(
                    "country",
                    "pick",
                    "Country",
                    source="countries",
                    default="ES",
                    display="country",
                ),
                Ask(
                    "region",
                    "pick",
                    "Region",
                    source="regions",
                    depends_on="country",
                    optional=True,
                    none_label="Only the national ones",
                    help="Your city's are in no source: if your city council "
                    "publishes a .ics, paste it separately.",
                ),
            ),
        ),
        sync=Sync("calendar", sync),
        clean=clean_settings,
        searches={"countries": search_countries, "regions": search_regions},
    ),
)
