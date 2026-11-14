from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Literal

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

SEARCH = "https://itunes.apple.com/search"

STORES = ("es", "us")


def timeout() -> float:
    return float(os.environ.get("PODCASTS_SOURCE_TIMEOUT_SECONDS", "10"))


class SourceFailed(Exception):
    pass


@dataclass
class Candidate:
    id: str
    title: str
    show: str | None = None
    url: str | None = None
    episodes: int | None = None
    minutes: int | None = None
    year: int | None = None
    store: str | None = None


def _candidate(raw: dict, kind: str, store: str) -> Candidate | None:
    title = raw.get("trackName") or raw.get("collectionName")
    ident = raw.get("trackId") or raw.get("collectionId")
    if not title or not ident:
        return None
    released = str(raw.get("releaseDate") or "")[:4]
    millis = raw.get("trackTimeMillis")
    url = raw.get("trackViewUrl") if kind == "episode" else raw.get("collectionViewUrl")
    url = url or raw.get("collectionViewUrl") or raw.get("trackViewUrl")
    return Candidate(
        id=str(ident),
        title=str(title),
        show=raw.get("collectionName") if kind == "episode" else raw.get("artistName"),
        url=str(url) if url and str(url).startswith("https://") else None,
        episodes=raw.get("trackCount") if kind == "podcast" else None,
        minutes=round(millis / 60000) if kind == "episode" and millis else None,
        year=int(released) if released.isdigit() else None,
        store=store,
    )


async def search(
    client: httpx.AsyncClient, query: str, kind: Literal["podcast", "episode"], limit: int
) -> list[dict]:
    entity = "podcastEpisode" if kind == "episode" else "podcast"
    for store in STORES:
        try:
            response = await client.get(
                SEARCH,
                params={
                    "term": query,
                    "media": "podcast",
                    "entity": entity,
                    "country": store,
                    "limit": str(limit),
                },
                headers={"user-agent": USER_AGENT},
                timeout=timeout(),
            )
        except httpx.HTTPError as error:
            raise SourceFailed(f"Apple Podcasts no contesta ({type(error).__name__})") from error
        if response.status_code != 200:
            raise SourceFailed(f"Apple Podcasts contesta {response.status_code}")
        try:
            results = response.json().get("results") or []
        except ValueError as error:
            raise SourceFailed("Apple Podcasts no devuelve JSON") from error
        found = [one for one in (_candidate(raw, kind, store) for raw in results) if one]
        if found:
            return [asdict(one) for one in found[:limit]]
    return []


SOURCES = (
    Provider(
        id="apple_podcasts",
        name="Apple Podcasts",
        category="leisure",
        description="Checks that a podcast or an episode exists before Insights "
        "recommends it, with its link. No key: it connects by itself "
        "the first time.",
        capabilities=("lookup",),
        serves=("podcasts.search",),
        available=True,
        single=True,
    ),
)
