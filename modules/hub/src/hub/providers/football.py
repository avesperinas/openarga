from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from hub.declare import Ask, Offer, Provider, Setting, Sync
from hub.providers import SourceError
from hub.providers.calendars import Item, events

PROVIDER = "football"
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
TEAM = "team"
TEAM_NAME = "team_name"
LEAGUE = "league"
MATCH = timedelta(hours=2)
MADRID = ZoneInfo("Europe/Madrid")

LEAGUES: dict[str, str] = {
    "esp.1": "LaLiga",
    "esp.2": "LaLiga Hypermotion",
    "eng.1": "Premier League",
    "ita.1": "Serie A",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "por.1": "Liga Portugal",
    "ned.1": "Eredivisie",
}
CUPS: dict[str, tuple[str, str]] = {
    "esp": ("esp.copa_del_rey", "Copa del Rey"),
    "eng": ("eng.fa", "FA Cup"),
    "ita": ("ita.coppa_italia", "Coppa Italia"),
    "ger": ("ger.dfb_pokal", "DFB-Pokal"),
    "fra": ("fra.coupe_de_france", "Copa de Francia"),
    "por": ("por.taca.portugal", "Taça de Portugal"),
    "ned": ("ned.cup", "KNVB Beker"),
}
EUROPE: dict[str, str] = {
    "uefa.champions": "Champions League",
    "uefa.europa": "Europa League",
    "uefa.europa.conf": "Conference League",
}
CANCELLED = ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_ABANDONED")


def clean_settings(raw: dict[str, Any]) -> dict[str, Any]:
    team = str(raw.get(TEAM) or "").strip()
    if not re.fullmatch(r"[0-9]{1,8}", team):
        raise ValueError("elige el equipo en el buscador")
    league = str(raw.get(LEAGUE) or "esp.1").strip()
    if league not in LEAGUES:
        raise ValueError(f"la liga tiene que ser una de {', '.join(LEAGUES)}")
    name = " ".join(str(raw.get(TEAM_NAME) or "").split())[:80] or None
    return {TEAM: team, LEAGUE: league, TEAM_NAME: name}


def competitions(league: str) -> dict[str, str]:
    found = {league: LEAGUES.get(league, league)}
    cup = CUPS.get(league.split(".")[0])
    if cup:
        found[cup[0]] = cup[1]
    return {**found, **EUROPE}


async def _get(client: httpx.AsyncClient, path: str, required: bool) -> dict[str, Any]:
    try:
        response = await client.get(f"{BASE}{path}", timeout=20.0)
    except httpx.HTTPError as error:
        if not required:
            return {}
        raise SourceError(f"ESPN no contesta ({type(error).__name__})", transient=True) from error
    if response.status_code == 429:
        raise SourceError("ESPN pide esperar", rate_limited=True)
    if response.status_code >= 400 or not response.content:
        if not required:
            return {}
        transient = response.status_code >= 500
        raise SourceError(f"ESPN contesta {response.status_code}", transient=transient)
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
        finished = status == "STATUS_FULL_TIME"
        score = _score(competition) if finished else None
        details = [competition_name]
        if score:
            details.append(score)
        if not timed:
            details.append("hora por confirmar")
        if status == "STATUS_POSTPONED":
            details.append("aplazado")
        if timed:
            first, last = start.isoformat(), (start + MATCH).isoformat()
        else:
            day = start.astimezone(MADRID).date()
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
        required = slug == league
        for query in ("", "?fixture=true"):
            found = await _get(client, f"/{slug}/teams/{team}/schedule{query}", required)
            for item in items_of(found.get("events") or [], name):
                items[item.uid] = item
    if not items:
        raise SourceError("ESPN no da ningún partido de ese equipo")
    return list(items.values())


async def sync(client: httpx.AsyncClient, _secrets: dict[str, str], connection: Any) -> list[dict]:
    config = connection.config or {}
    now = datetime.now(UTC)
    items = await fetch(client, config.get(TEAM) or "", config.get(LEAGUE) or "esp.1")
    return events(connection, connection.provider, items, now)


async def teams(client: httpx.AsyncClient, query: str) -> list[dict[str, str]]:
    needle = _fold(query)
    found: list[dict[str, str]] = []
    for slug, league in LEAGUES.items():
        body = await _get(client, f"/{slug}/teams", required=False)
        for entry in ((body.get("sports") or [{}])[0].get("leagues") or [{}])[0].get("teams") or []:
            team = entry.get("team") or {}
            name = team.get("displayName") or ""
            if needle and needle in _fold(name):
                found.append(
                    {
                        "code": str(team.get("id")),
                        "name": name,
                        "league": slug,
                        "league_name": league,
                        "detail": league,
                    }
                )
    return found[:20]


async def search_teams(
    client: httpx.AsyncClient, query: str | None, _parent: str | None
) -> list[dict[str, str]]:
    if not query or len(query.strip()) < 2:
        raise ValueError("escribe el nombre del equipo")
    return await teams(client, query.strip())


def _fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return plain.casefold().strip()


SOURCES = (
    Provider(
        id="football",
        name="Fútbol",
        category="calendar",
        description="Los partidos de un equipo, de ESPN: liga, copa y Europa, con el resultado de "
        "lo jugado. Hasta que se fija la hora de un partido va como «hora por confirmar», y cuando "
        "se fija pasa a su hora. Se suscribe desde Planner.",
        capabilities=("sync",),
        settings=(
            Setting("team", "Equipo", "Su número en ESPN; desde Planner se elige por su nombre."),
            Setting("league", "Liga", "Como esp.1 para LaLiga.", "esp.1"),
            Setting("team_name", "Nombre", "Cómo se llama el equipo."),
        ),
        emits=("calendar.event", "calendar.feed"),
        available=True,
        schedule="20 */6 * * *",
        offer=Offer(
            title="Fútbol",
            subtitle="Los partidos de los equipos que elijas: liga, copa y Europa",
            tone=2,
            many=True,
            group="sport",
            name="{team}",
            asks=(
                Ask(
                    "team",
                    "lookup",
                    "Equipo",
                    source="teams",
                    carries=(("league", "league"), ("name", "team_name")),
                    placeholder="Osasuna, Athletic, Arsenal…",
                    help="Cualquier equipo. Hasta que se fija la hora de un partido sale como "
                    "«hora por confirmar».",
                ),
            ),
        ),
        sync=Sync("calendar", sync),
        clean=clean_settings,
        searches={"teams": search_teams},
    ),
)
