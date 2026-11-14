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
        raise ValueError("paste the whole address, starting with https:// or webcal://")
    if len(value) > 2000:
        raise ValueError("the address is too long")
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
        raise SourceError(f"not an iCalendar calendar: {error}") from error
    fallback = str(calendar.get("X-WR-TIMEZONE") or "UTC")
    try:
        ZoneInfo(fallback)
    except (KeyError, ValueError):
        fallback = "UTC"
    first, last = window(today)
    repeating = _repeating(calendar)
    try:
        found = recurring_ical_events.of(calendar).between(first, last + timedelta(days=1))
    except Exception as error:  # noqa: BLE001 - a malformed calendar is reported, it breaks nothing
        raise SourceError(f"the calendar cannot be read: {type(error).__name__} {error}") from error
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
                title=clip(str(component.get("SUMMARY") or ""), 200) or "(untitled)",
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
            f"the calendar does not answer ({type(error).__name__})", transient=True
        ) from error
    if response.status_code == 429:
        raise SourceError("the calendar server asks to wait", rate_limited=True)
    if response.status_code >= 500:
        raise SourceError(f"the calendar server fails ({response.status_code})", transient=True)
    if response.status_code in (401, 403, 404, 410):
        raise SourceError(
            f"the address no longer gives the calendar ({response.status_code}): "
            "check that it is still published"
        )
    if response.status_code >= 400:
        raise SourceError(f"the calendar server answers {response.status_code}")
    if len(response.content) > MAX_BYTES:
        raise SourceError("el calendario pesa demasiado para suscribirse")
    return response.content


async def sync(client: httpx.AsyncClient, secrets: dict[str, str], connection: Any) -> list[dict]:
    url = secrets.get(URL) or (connection.config or {}).get(URL)
    if not url:
        raise SourceError("the subscription has no address")
    now = datetime.now(UTC)
    body = await download(client, url)
    return events(connection, connection.provider, parse(body, now.date()), now)


SOURCES = (
    Provider(
        id="ical",
        name="Published calendar",
        category="calendar",
        description="Any calendar published in iCalendar, by its .ics or "
        "webcal:// address: a team's, your city's holidays, one "
        "shared with you. Updated every day. Subscribed from Planner.",
        capabilities=("sync",),
        settings=(Setting("url", "Address", "The one starting with https:// or webcal://."),),
        emits=("calendar.event", "calendar.feed"),
        available=True,
        schedule="15 4 * * *",
        offer=Offer(
            title="Another calendar",
            subtitle="Any .ics or webcal:// calendar: a series, a festival, another sport",
            tone=7,
            many=True,
            group="other",
            name="{url}",
            asks=(
                Ask(
                    "url",
                    "url",
                    "Address",
                    placeholder="https://… or webcal://…",
                    help="If it is private, like an iCloud calendar's, paste it "
                    "in Hub: it is stored encrypted there.",
                ),
            ),
        ),
        sync=Sync("calendar", sync),
        normalise=normalise,
        clean=clean_settings,
    ),
    Provider(
        id="ical_private",
        name="Private calendar",
        category="calendar",
        description="A .ics calendar whose address is secret, like an iCloud one:"
        " the address is stored encrypted, like a key. It shows in "
        "Planner as one more subscription.",
        capabilities=("sync",),
        secrets=(
            Secret(
                "url",
                "Private address",
                "The .ics or webcal:// address your calendar gives when you share"
                " it. Whoever has it can read it, so it is stored as a secret.",
            ),
        ),
        emits=("calendar.event", "calendar.feed"),
        available=True,
        schedule="15 4 * * *",
        sync=Sync("calendar", sync),
        normalise=normalise,
    ),
)
