from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from hub.declare import Ask, Choice, Offer, Provider, Setting, Sync
from hub.providers import SourceError
from hub.providers.calendars import Item, events, window

PROVIDER = "formula1"
BASE = "https://api.jolpi.ca/ergast/f1"
SESSIONS_KEY = "sessions"

SESSIONS: dict[str, tuple[str, str, timedelta]] = {
    "race": ("", "Race", timedelta(hours=2)),
    "qualifying": ("Qualifying", "Qualifying", timedelta(hours=1)),
    "sprint": ("Sprint", "Sprint", timedelta(minutes=45)),
    "sprint_qualifying": ("SprintQualifying", "Sprint qualifying", timedelta(minutes=45)),
    "practice": ("", "Practice", timedelta(hours=1)),
}
PRACTICE = (
    ("FirstPractice", "Practice 1"),
    ("SecondPractice", "Practice 2"),
    ("ThirdPractice", "Practice 3"),
)
DEFAULT = ("race", "qualifying", "sprint")


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    chosen = raw.get(SESSIONS_KEY)
    if chosen in (None, "", []):
        chosen = list(DEFAULT)
    if isinstance(chosen, str):
        chosen = [part.strip() for part in chosen.split(",") if part.strip()]
    unknown = sorted(set(chosen) - set(SESSIONS))
    if unknown:
        raise ValueError(f"sessions that do not exist: {', '.join(unknown)}")
    if not chosen:
        raise ValueError("choose at least one session")
    return {SESSIONS_KEY: [key for key in SESSIONS if key in chosen]}


def _moment(block: dict[str, Any]) -> datetime | None:
    if not block.get("date"):
        return None
    clock = block.get("time") or "12:00:00Z"
    return datetime.fromisoformat(f"{block['date']}T{clock.replace('Z', '+00:00')}")


def _name(race: dict[str, Any]) -> str:
    return race.get("raceName") or "Grand Prix"


def items_of(races: list[dict[str, Any]], sessions: list[str]) -> list[Item]:
    items: list[Item] = []
    for race in races:
        season, round_ = race.get("season"), race.get("round")
        name = _name(race)
        circuit = race.get("Circuit") or {}
        location = ", ".join(
            filter(
                None,
                [
                    circuit.get("circuitName"),
                    (circuit.get("Location") or {}).get("locality"),
                ],
            )
        )
        wanted: list[tuple[str, str, dict[str, Any], timedelta]] = []
        if "race" in sessions:
            wanted.append(("race", SESSIONS["race"][1], race, SESSIONS["race"][2]))
        for key in ("qualifying", "sprint", "sprint_qualifying"):
            source, label, length = SESSIONS[key]
            if key in sessions and race.get(source):
                wanted.append((key, label, race[source], length))
        if "practice" in sessions:
            for source, label in PRACTICE:
                if race.get(source):
                    wanted.append((source.lower(), label, race[source], SESSIONS["practice"][2]))
        for key, label, block, length in wanted:
            start = _moment(block)
            if start is None:
                continue
            items.append(
                Item(
                    uid=f"f1:{season}:{round_}:{key}",
                    title=f"{name} · {label}",
                    all_day=False,
                    start=start.isoformat(),
                    end=(start + length).isoformat(),
                    tz="UTC",
                    location=location or None,
                    url=race.get("url")
                    if str(race.get("url", "")).startswith("https://")
                    else None,
                )
            )
    return items


async def season(client: httpx.AsyncClient, year: int) -> list[dict[str, Any]]:
    try:
        response = await client.get(f"{BASE}/{year}/races/", params={"limit": 100}, timeout=20.0)
    except httpx.HTTPError as error:
        raise SourceError(
            f"Jolpica no contesta ({type(error).__name__})", transient=True
        ) from error
    if response.status_code == 429:
        raise SourceError("Jolpica pide esperar", rate_limited=True)
    if response.status_code >= 500:
        raise SourceError(f"Jolpica falla ({response.status_code})", transient=True)
    if response.status_code >= 400:
        raise SourceError(f"Jolpica contesta {response.status_code}")
    return response.json().get("MRData", {}).get("RaceTable", {}).get("Races", [])


async def fetch(client: httpx.AsyncClient, sessions: list[str], today: date) -> list[Item]:
    first, last = window(today)
    items: list[Item] = []
    for year in range(first.year, last.year + 1):
        races = await season(client, year)
        if not races and year == today.year:
            raise SourceError(f"Jolpica does not give the season {year}")
        items.extend(items_of(races, sessions))
    return items


async def sync(client: httpx.AsyncClient, _secrets: dict[str, str], connection: Any) -> list[dict]:
    config = connection.config or {}
    sessions = config.get(SESSIONS_KEY) or list(DEFAULT)
    now = datetime.now(UTC)
    return events(connection, connection.provider, await fetch(client, sessions, now.date()), now)


SOURCES = (
    Provider(
        id="formula1",
        name="Formula 1",
        category="calendar",
        description="The Formula 1 calendar with the sessions you choose, from "
        "Jolpica: if a race changes or is cancelled, it changes or "
        "disappears from your calendar. Subscribed from Planner.",
        capabilities=("sync",),
        settings=(
            Setting(
                "sessions",
                "Sessions",
                "Comma separated: race, qualifying, sprint, sprint_qualifying, practice.",
                "race,qualifying,sprint",
            ),
        ),
        emits=("calendar.event", "calendar.feed"),
        available=True,
        schedule="45 3 * * *",
        offer=Offer(
            title="Formula 1",
            subtitle="Races, qualifying and sprints, in your time zone",
            tone=1,
            group="sport",
            name="Formula 1",
            asks=(
                Ask(
                    "sessions",
                    "checks",
                    "Sessions",
                    choices=(
                        Choice("race", "Race"),
                        Choice("qualifying", "Qualifying"),
                        Choice("sprint", "Sprint"),
                        Choice("sprint_qualifying", "Sprint qualifying"),
                        Choice("practice", "Practice"),
                    ),
                    defaults=("race", "qualifying", "sprint"),
                ),
            ),
        ),
        sync=Sync("calendar", sync),
        clean=clean_settings,
    ),
)
