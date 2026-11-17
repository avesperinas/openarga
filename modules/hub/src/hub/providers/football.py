from __future__ import annotations

import asyncio
import re
import tomllib
import unicodedata
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import httpx

from arga_module import preferences
from hub import words
from hub.declare import Ask, Offer, Provider, Setting, Sync
from hub.providers import SourceError
from hub.providers.calendars import Item, events

PROVIDER = "football"
BASE = "https://site.api.espn.com/apis/site/v2/sports"
TEAM = "team"
TEAM_NAME = "team_name"
LEAGUE = "league"
SOCCER = "soccer"
MATCH = timedelta(hours=2)
CATALOGUE = Path(__file__).resolve().parent.parent / "catalogs" / "espn.toml"
CANCELLED = ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_ABANDONED")
FINISHED = ("STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_OT", "STATUS_FINAL_PEN")


@cache
def sports() -> dict[str, dict[str, Any]]:
    return tomllib.loads(CATALOGUE.read_text())


@cache
def leagues() -> dict[str, str]:
    found = {}
    for sport, data in sports().items():
        for slug, name in data.get("leagues", {}).items():
            found[slug if sport == SOCCER else f"{sport}/{slug}"] = name
    return found


def path_of(league: str) -> str:
    return league if "/" in league else f"{SOCCER}/{league}"


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    team = str(raw.get(TEAM) or "").strip()
    if not re.fullmatch(r"[0-9]{1,8}", team):
        raise ValueError("choose the team in the search")
    league = str(raw.get(LEAGUE) or "esp.1").strip()
    if league not in leagues():
        raise ValueError(f"the league must be one of {', '.join(leagues())}")
    name = " ".join(str(raw.get(TEAM_NAME) or "").split())[:80] or None
    return {TEAM: team, LEAGUE: league, TEAM_NAME: name}


def competitions(league: str) -> dict[str, str]:
    found = {path_of(league): leagues().get(league, league)}
    if "/" in league:
        return found
    soccer = sports()[SOCCER]
    country = league.split(".")[0]
    cup = soccer.get("cups", {}).get(country)
    if cup:
        found[f"{SOCCER}/{cup[0]}"] = cup[1]
    if country in soccer.get("continental_for", ()):
        found.update({f"{SOCCER}/{slug}": name for slug, name in soccer["continental"].items()})
    return found


async def _get(client: httpx.AsyncClient, path: str, required: bool) -> dict[str, Any]:
    try:
        response = await client.get(f"{BASE}{path}", timeout=20.0)
    except httpx.HTTPError as error:
        if not required:
            return {}
        raise SourceError(
            f"ESPN does not answer ({type(error).__name__})", transient=True
        ) from error
    if response.status_code == 429:
        raise SourceError("ESPN asks to wait", rate_limited=True)
    if response.status_code >= 400 or not response.content:
        if not required:
            return {}
        transient = response.status_code >= 500
        raise SourceError(f"ESPN answers {response.status_code}", transient=transient)
    return response.json()


def _side(competition: dict[str, Any], where: str) -> str:
    for one in competition.get("competitors") or []:
        if one.get("homeAway") == where:
            return (one.get("team") or {}).get("displayName") or "?"
    return "?"


def _score(competition: dict[str, Any]) -> str | None:
    scores = {}
    for one in competition.get("competitors") or []:
        value = one.get("score")
        if isinstance(value, dict):
            value = value.get("displayValue")
        scores[one.get("homeAway")] = value
    if scores.get("home") in (None, "") or scores.get("away") in (None, ""):
        return None
    return f"{scores['home']}–{scores['away']}"


def items_of(found: list[dict[str, Any]], competition_name: str) -> list[Item]:
    items: list[Item] = []
    for event in found:
        competition = (event.get("competitions") or [{}])[0]
        if not event.get("date"):
            continue
        start = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        status = ((competition.get("status") or {}).get("type") or {}).get("name", "")
        timed = bool(event.get("timeValid", competition.get("timeValid", True)))
        title = f"{_side(competition, 'home')} – {_side(competition, 'away')}"
        venue = competition.get("venue") or {}
        city = (venue.get("address") or {}).get("city")
        location = ", ".join(filter(None, [venue.get("fullName"), city])) or None
        finished = status in FINISHED
        score = _score(competition) if finished else None
        details = [competition_name]
        if score:
            details.append(score)
        if not timed:
            details.append(words.say("game.untimed"))
        if status == "STATUS_POSTPONED":
            details.append(words.say("game.postponed"))
        if timed:
            first, last = start.isoformat(), (start + MATCH).isoformat()
        else:
            day = start.astimezone(preferences.current().zone).date()
            first, last = day.isoformat(), (day + timedelta(days=1)).isoformat()
        items.append(
            Item(
                uid=f"espn:{event.get('id')}",
                title=title,
                all_day=not timed,
                start=first,
                end=last,
                tz="UTC",
                location=location,
                description=" · ".join(details),
                status="cancelled" if status in CANCELLED else "confirmed",
            )
        )
    return items


async def fetch(client: httpx.AsyncClient, team: str, league: str) -> list[Item]:
    items: dict[str, Item] = {}
    for slug, name in competitions(league).items():
        required = slug == path_of(league)
        for query in ("", "?fixture=true"):
            found = await _get(client, f"/{slug}/teams/{team}/schedule{query}", required)
            for item in items_of(found.get("events") or [], name):
                items[item.uid] = item
    if not items:
        raise SourceError("ESPN gives no match for that team")
    return list(items.values())


async def sync(client: httpx.AsyncClient, _secrets: dict[str, str], connection: Any) -> list[dict]:
    config = connection.config or {}
    now = datetime.now(UTC)
    items = await fetch(client, config.get(TEAM) or "", config.get(LEAGUE) or "esp.1")
    return events(connection, connection.provider, items, now)


async def teams(client: httpx.AsyncClient, query: str) -> list[dict[str, str]]:
    needle = _fold(query)

    async def one_league(league: str, name: str) -> list[dict[str, str]]:
        body = await _get(client, f"/{path_of(league)}/teams", required=False)
        found = []
        for entry in ((body.get("sports") or [{}])[0].get("leagues") or [{}])[0].get("teams") or []:
            team = entry.get("team") or {}
            label = team.get("displayName") or ""
            if needle and needle in _fold(label):
                found.append(
                    {
                        "code": str(team.get("id")),
                        "name": label,
                        "league": league,
                        "league_name": name,
                        "detail": name,
                    }
                )
        return found

    answers = await asyncio.gather(*(one_league(*pair) for pair in leagues().items()))
    return [team for answer in answers for team in answer][:20]


async def search_teams(
    client: httpx.AsyncClient, query: str | None, _parent: str | None
) -> list[dict[str, str]]:
    if not query or len(query.strip()) < 2:
        raise ValueError("type the team's name")
    return await teams(client, query.strip())


def _fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return plain.casefold().strip()


SOURCES = (
    Provider(
        id="football",
        name="Sport",
        category="calendar",
        description="A team's games, from ESPN: football with its cup and Europe, basketball,"
        " American football, baseball and ice hockey, with the result of those played."
        ' Until a game\'s time is set it shows as "time to be confirmed", and once set it'
        " moves to its time. Subscribed from Planner.",
        capabilities=("sync",),
        settings=(
            Setting("team", "Team", "Its ESPN number; Planner lets you choose it by name."),
            Setting("league", "League", "Like esp.1 for LaLiga or basketball/nba.", "esp.1"),
            Setting("team_name", "Name", "The team's name."),
        ),
        emits=("calendar.event", "calendar.feed"),
        available=True,
        schedule="20 */6 * * *",
        offer=Offer(
            title="Sport",
            subtitle="The games of the teams you choose, in any sport ESPN follows",
            tone=2,
            many=True,
            group="sport",
            name="{team}",
            asks=(
                Ask(
                    "team",
                    "lookup",
                    "Team",
                    source="teams",
                    carries=(("league", "league"), ("name", "team_name")),
                    placeholder="Osasuna, Arsenal, Lakers, Yankees…",
                    help="Any team. Until a match's time is set it shows as \"time"
                    ' to be confirmed".',
                ),
            ),
        ),
        sync=Sync("calendar", sync),
        clean=clean_settings,
        searches={"teams": search_teams},
    ),
)
