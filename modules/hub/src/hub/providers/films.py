from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import quote

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

API = "https://www.wikidata.org/w/api.php"

FILMS = frozenset(
    {
        "Q11424",
        "Q24869",
        "Q202866",
        "Q506240",
        "Q24862",
    }
)
DOCUMENTARIES = frozenset({"Q93204"})
SERIES = frozenset(
    {
        "Q5398426",
        "Q1259759",
        "Q526877",
        "Q581714",
        "Q63952888",
    }
)
WANTED: dict[str, frozenset[str]] = {
    "film": FILMS | DOCUMENTARIES,
    "series": SERIES | DOCUMENTARIES,
    "documentary": DOCUMENTARIES | FILMS | SERIES,
}


def timeout() -> float:
    return float(os.environ.get("WIKIDATA_SOURCE_TIMEOUT_SECONDS", "15"))


class SourceFailed(Exception):
    pass


@dataclass
class Candidate:
    id: str
    title: str
    year: int | None = None
    creators: list[str] = field(default_factory=list)
    minutes: int | None = None
    seasons: int | None = None
    wikipedia: str | None = None


async def _get(client: httpx.AsyncClient, params: dict[str, str]) -> dict[str, Any]:
    try:
        response = await client.get(
            API,
            params={**params, "format": "json"},
            headers={"user-agent": USER_AGENT},
            timeout=timeout(),
        )
    except httpx.HTTPError as error:
        raise SourceFailed(f"Wikidata no contesta ({type(error).__name__})") from error
    if response.status_code != 200:
        raise SourceFailed(f"Wikidata contesta {response.status_code}")
    try:
        return response.json()
    except ValueError as error:
        raise SourceFailed("Wikidata no devuelve JSON") from error


def _ids(claims: dict, prop: str) -> list[str]:
    out = []
    for claim in claims.get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.append(value["id"])
    return out


def _year(claims: dict) -> int | None:
    years = []
    for claim in claims.get("P577", []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        stamp = str(value.get("time", "")) if isinstance(value, dict) else ""
        if len(stamp) >= 5 and stamp[1:5].isdigit():
            years.append(int(stamp[1:5]))
    return min(years) if years else None


def _amount(claims: dict, prop: str) -> int | None:
    for claim in claims.get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(value, dict) and value.get("amount"):
            try:
                return round(abs(float(value["amount"])))
            except ValueError:
                return None
    return None


def _label(entity: dict) -> str | None:
    labels = entity.get("labels", {})
    for language in ("es", "en"):
        if labels.get(language, {}).get("value"):
            return labels[language]["value"]
    return None


def _wikipedia(entity: dict) -> str | None:
    links = entity.get("sitelinks", {})
    for wiki, host in (("eswiki", "es"), ("enwiki", "en")):
        title = links.get(wiki, {}).get("title")
        if title:
            return f"https://{host}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
    return None


async def search(
    client: httpx.AsyncClient,
    query: str,
    kind: Literal["film", "series", "documentary"],
    limit: int,
) -> list[dict]:
    found = await _get(
        client,
        {
            "action": "wbsearchentities",
            "search": query,
            "language": "es",
            "uselang": "es",
            "type": "item",
            "limit": "15",
        },
    )
    ids = [one["id"] for one in found.get("search", []) if one.get("id")]
    if not ids:
        return []
    entities = (
        await _get(
            client,
            {
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": "labels|claims|sitelinks",
                "languages": "es|en",
            },
        )
    ).get("entities", {})
    wanted = WANTED[kind]
    chosen = [
        entities[one]
        for one in ids
        if one in entities and set(_ids(entities[one].get("claims", {}), "P31")) & wanted
    ][:limit]
    people = sorted(
        {
            person
            for entity in chosen
            for person in _ids(entity.get("claims", {}), "P57")[:2]
            + _ids(entity.get("claims", {}), "P170")[:2]
        }
    )
    names: dict[str, str] = {}
    if people:
        named = (
            await _get(
                client,
                {
                    "action": "wbgetentities",
                    "ids": "|".join(people[:40]),
                    "props": "labels",
                    "languages": "es|en",
                },
            )
        ).get("entities", {})
        names = {key: label for key, value in named.items() if (label := _label(value))}
    out = []
    for entity in chosen:
        claims = entity.get("claims", {})
        title = _label(entity)
        if not title:
            continue
        creators = [
            names[person]
            for person in _ids(claims, "P57")[:2] + _ids(claims, "P170")[:2]
            if person in names
        ]
        out.append(
            Candidate(
                id=entity["id"],
                title=title,
                year=_year(claims),
                creators=creators,
                minutes=_amount(claims, "P2047"),
                seasons=_amount(claims, "P2437"),
                wikipedia=_wikipedia(entity),
            )
        )
    return [asdict(one) for one in out]


SOURCES = (
    Provider(
        id="wikidata",
        name="Wikidata",
        category="leisure",
        description="Comprobar que una película, una serie o un documental existe antes de que "
        "Insights te lo recomiende, con su año, quién la dirige y su artículo de Wikipedia. Sin "
        "clave: se conecta sola la primera vez.",
        capabilities=("lookup",),
        serves=("films.search",),
        available=True,
        single=True,
    ),
)
