from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from hub.declare import Ask, Offer, Provider, Secret, Setting, Sync
from hub.providers import SourceError
from hub.providers.calendars import Item, clip, events, window

PROVIDER = "ical"
PRIVATE = "ical_private"
URL = "url"
MAX_BYTES = 10 * 1024 * 1024


def clean_url(raw: str) -> str:
    value = raw.strip()
    if value.lower().startswith("webcal://"):
        value = "https://" + value[len("webcal://") :]
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or " " in value:
        raise ValueError("pega la dirección entera, empezando por https:// o webcal://")
    if len(value) > 2000:
        raise ValueError("la dirección es demasiado larga")
    return value


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    return {URL: clean_url(str(raw.get(URL) or ""))}


def normalise(_key: str, raw: str) -> str:
    return clean_url(raw)


def _when(value: date | datetime, tz: str) -> tuple[str, bool]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo(tz))
        return value.isoformat(), False
    return value.isoformat(), True


def _zone_of(component: Any, fallback: str) -> str:
    start = component.get("DTSTART")
    tzid = start.params.get("TZID") if start is not None else None
    if tzid:
        try:
            ZoneInfo(str(tzid))
            return str(tzid)
        except (KeyError, ValueError):
            pass
    moment = component.decoded("DTSTART")
    if isinstance(moment, datetime) and moment.tzinfo is not None:
        key = getattr(moment.tzinfo, "key", None)
        if key:
            return key
        if moment.utcoffset() == timedelta(0):
            return "UTC"
    return fallback


def _repeating(calendar: Any) -> set[str]:
    return {
        str(component.get("UID"))
        for component in calendar.walk("VEVENT")
        if any(key in component for key in ("RRULE", "RDATE", "RECURRENCE-ID"))
    }


def _uid(component: Any, index: int, repeating: set[str]) -> str:
    base = str(component.get("UID") or f"sin-uid-{index}")
    original = component.get("RECURRENCE-ID")
    if original is None or base not in repeating:
        return base
    moment = original.dt
    stamp = moment.isoformat()
    if isinstance(moment, datetime) and moment.tzinfo is not None:
        stamp = moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{base}#{stamp}"


def parse(body: bytes, today: date) -> list[Item]:
    try:
        calendar = icalendar.Calendar.from_ical(body)
    except ValueError as error:
        raise SourceError(f"no es un calendario iCalendar: {error}") from error
    fallback = str(calendar.get("X-WR-TIMEZONE") or "UTC")
    try:
        ZoneInfo(fallback)
    except (KeyError, ValueError):
        fallback = "UTC"
    first, last = window(today)
    repeating = _repeating(calendar)
    try:
        found = recurring_ical_events.of(calendar).between(first, last + timedelta(days=1))
    except Exception as error:  # noqa: BLE001 - un calendario mal formado se dice, no tumba nada
        raise SourceError(
            f"el calendario no se puede leer: {type(error).__name__} {error}"
        ) from error
    items: list[Item] = []
    for index, component in enumerate(found):
        if "DTSTART" not in component:
            continue
        tz = _zone_of(component, fallback)
        start, all_day = _when(component.decoded("DTSTART"), tz)
        if "DTEND" in component:
            end, _ = _when(component.decoded("DTEND"), tz)
        elif all_day:
            end = (date.fromisoformat(start) + timedelta(days=1)).isoformat()
        else:
            end = start
        if all_day and end <= start:
            end = (date.fromisoformat(start) + timedelta(days=1)).isoformat()
        status = str(component.get("STATUS") or "").upper()
        url = str(component.get("URL") or "") or None
        items.append(
            Item(
                uid=_uid(component, index, repeating),
                title=clip(str(component.get("SUMMARY") or ""), 200) or "(sin título)",
                all_day=all_day,
                start=start,
                end=end,
                tz="UTC" if all_day else tz,
                location=clip(str(component.get("LOCATION") or "") or None, 300),
                description=clip(str(component.get("DESCRIPTION") or "") or None, 8000),
                url=url if url and re.match(r"^https?://", url) else None,
                status="cancelled" if status == "CANCELLED" else "confirmed",
            )
        )
    return items


async def download(client: httpx.AsyncClient, url: str) -> bytes:
    try:
        response = await client.get(
            url,
            follow_redirects=True,
            timeout=30.0,
            headers={"accept": "text/calendar, */*;q=0.5", "user-agent": "arga (calendario)"},
        )
    except httpx.HTTPError as error:
        raise SourceError(
            f"el calendario no contesta ({type(error).__name__})", transient=True
        ) from error
    if response.status_code == 429:
        raise SourceError("el servidor del calendario pide esperar", rate_limited=True)
    if response.status_code >= 500:
        raise SourceError(
            f"el servidor del calendario falla ({response.status_code})", transient=True
        )
    if response.status_code in (401, 403, 404, 410):
        raise SourceError(
            f"la dirección ya no da el calendario ({response.status_code}): "
            "comprueba que sigue publicado"
        )
    if response.status_code >= 400:
        raise SourceError(f"el servidor del calendario contesta {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise SourceError("el calendario pesa demasiado para suscribirse")
    return response.content


async def sync(client: httpx.AsyncClient, secrets: dict[str, str], connection: Any) -> list[dict]:
    url = secrets.get(URL) or (connection.config or {}).get(URL)
    if not url:
        raise SourceError("la suscripción no tiene dirección")
    now = datetime.now(UTC)
    body = await download(client, url)
    return events(connection, connection.provider, parse(body, now.date()), now)


SOURCES = (
    Provider(
        id="ical",
        name="Calendario publicado",
        category="calendar",
        description="Cualquier calendario publicado en iCalendar, por su dirección .ics o "
        "webcal://: el de un equipo, los festivos de tu ciudad, uno que te comparten. Se "
        "actualiza cada día. Se suscribe desde Planner.",
        capabilities=("sync",),
        settings=(Setting("url", "Dirección", "La que empieza por https:// o webcal://."),),
        emits=("calendar.event", "calendar.feed"),
        available=True,
        schedule="15 4 * * *",
        offer=Offer(
            title="Otro calendario",
            subtitle="Cualquier calendario .ics o webcal://: una serie, un festival, otro deporte",
            tone=7,
            many=True,
            group="other",
            name="{url}",
            asks=(
                Ask(
                    "url",
                    "url",
                    "Dirección",
                    placeholder="https://… o webcal://…",
                    help="Si es privada, como la de un calendario de iCloud, pégala en "
                    "Hub: allí se guarda cifrada.",
                ),
            ),
        ),
        sync=Sync("calendar", sync),
        normalise=normalise,
        clean=clean_settings,
    ),
    Provider(
        id="ical_private",
        name="Calendario privado",
        category="calendar",
        description="Un calendario .ics cuya dirección es secreta, como la de uno de iCloud: la "
        "dirección se guarda cifrada, como una clave. Sale en Planner como una suscripción más.",
        capabilities=("sync",),
        secrets=(
            Secret(
                "url",
                "Dirección privada",
                "La dirección .ics o webcal:// que da tu calendario al compartirlo. Quien la tiene "
                "lo lee, por eso se guarda como un secreto.",
            ),
        ),
        emits=("calendar.event", "calendar.feed"),
        available=True,
        schedule="15 4 * * *",
        sync=Sync("calendar", sync),
        normalise=normalise,
    ),
)
