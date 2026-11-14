from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

WIKIDATA = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
OSM = "https://www.openstreetmap.org/api/0.6/{type}/{id}.json"
UPLOADS = frozenset({"upload.wikimedia.org", "thumb.wikimedia.org"})

WIDTH = 1600
MAX_BYTES = 8 * 1024 * 1024
NEAR_KM = 20
NEAR_PHOTO_KM = 10
AROUND_METRES = 3000
BITMAP = re.compile(r"\.(jpe?g|png|webp)$", re.IGNORECASE)
OSM_REF = re.compile(r"^(node|way|relation)/[0-9]+$")
QID = re.compile(r"^Q[0-9]+$")
FILLER = frozenset(
    "el la los las lo de del y e en con sus su a al por un una unos unas the".split()  # noqa: SIM905
)
SIGNATURES = ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"))


def timeout() -> float:
    return float(os.environ.get("WIKIMEDIA_SOURCE_TIMEOUT_SECONDS", "15"))


class SourceFailed(Exception):
    pass


@dataclass(frozen=True)
class Photo:
    content: bytes
    type: str
    author: str | None
    license: str | None
    page: str


def fold(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def phrases(name: str, place: str | None) -> list[str]:
    found = []
    for piece in re.split(r"[:,;]| y | e ", name):
        words = [word for word in re.findall(r"[\w'-]+", piece) if word.casefold() not in FILLER]
        if words:
            found.append(" ".join(words))
    if place:
        found.append(place.strip())
    return list(dict.fromkeys(one for one in found if len(one) >= 3))


def image_type(body: bytes) -> str | None:
    for signature, kind in SIGNATURES:
        if body.startswith(signature):
            return kind
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None


def plain(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = " ".join(text.split())
    return text[:200] or None


async def _json(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    try:
        response = await client.get(
            url, params=params, headers={"user-agent": USER_AGENT}, timeout=timeout()
        )
        if response.status_code in (404, 410):
            return {}
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as error:
        raise SourceFailed(f"Wikimedia no contestó: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("Wikimedia contestó algo que no es JSON") from error
    return payload if isinstance(payload, dict) else {}


async def _osm_entity(client: httpx.AsyncClient, osm_ref: str) -> str | None:
    kind, number = osm_ref.split("/")
    payload = await _json(client, OSM.format(type=kind, id=number))
    elements = payload.get("elements") or [{}]
    entity = str((elements[0].get("tags") or {}).get("wikidata") or "")
    return entity if QID.match(entity) else None


async def _near_entity(client: httpx.AsyncClient, words: str, lat: float, lon: float) -> str | None:
    payload = await _json(
        client,
        WIKIDATA,
        {
            "action": "query",
            "list": "search",
            "format": "json",
            "srlimit": 1,
            "srsearch": f"{words} haswbstatement:P18 nearcoord:{NEAR_KM}km,{lat},{lon}",
        },
    )
    hits = (payload.get("query") or {}).get("search") or []
    entity = str(hits[0].get("title") or "") if hits else ""
    return entity if QID.match(entity) else None


async def _entity_image(client: httpx.AsyncClient, entity: str) -> str | None:
    payload = await _json(
        client,
        WIKIDATA,
        {"action": "wbgetclaims", "entity": entity, "property": "P18", "format": "json"},
    )
    for claim in (payload.get("claims") or {}).get("P18") or []:
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, str) and value:
            return value
    return None


async def _near_file(client: httpx.AsyncClient, words: str, lat: float, lon: float) -> str | None:
    payload = await _json(
        client,
        COMMONS,
        {
            "action": "query",
            "list": "search",
            "format": "json",
            "srnamespace": 6,
            "srlimit": 1,
            "srsearch": f"{words} filetype:bitmap nearcoord:{NEAR_PHOTO_KM}km,{lat},{lon}",
        },
    )
    hits = (payload.get("query") or {}).get("search") or []
    title = str(hits[0].get("title") or "") if hits else ""
    return title.removeprefix("File:") or None


async def _named_entity(client: httpx.AsyncClient, words: str) -> str | None:
    payload = await _json(
        client,
        WIKIDATA,
        {
            "action": "query",
            "list": "search",
            "format": "json",
            "srlimit": 3,
            "srsearch": f"{words} haswbstatement:P18 -haswbstatement:P625",
        },
    )
    hits = [str(one.get("title") or "") for one in (payload.get("query") or {}).get("search") or []]
    hits = [one for one in hits if QID.match(one)]
    if not hits:
        return None
    found = await _json(
        client,
        WIKIDATA,
        {
            "action": "wbgetentities",
            "ids": "|".join(hits),
            "props": "labels|aliases",
            "languages": "es|eu|en",
            "format": "json",
        },
    )
    wanted = fold(words)
    for entity in hits:
        about = (found.get("entities") or {}).get(entity) or {}
        names = [one.get("value", "") for one in (about.get("labels") or {}).values()]
        names += [
            one.get("value", "") for many in (about.get("aliases") or {}).values() for one in many
        ]
        if any(fold(name) == wanted for name in names):
            return entity
    return None


async def _around_file(client: httpx.AsyncClient, lat: float, lon: float) -> str | None:
    payload = await _json(
        client,
        COMMONS,
        {
            "action": "query",
            "list": "geosearch",
            "format": "json",
            "gscoord": f"{lat}|{lon}",
            "gsradius": AROUND_METRES,
            "gsnamespace": 6,
            "gslimit": 20,
        },
    )
    for one in (payload.get("query") or {}).get("geosearch") or []:
        title = str(one.get("title") or "").removeprefix("File:")
        if BITMAP.search(title):
            return title
    return None


async def find_file(
    client: httpx.AsyncClient,
    name: str,
    place: str | None,
    osm_ref: str | None,
    lat: float | None,
    lon: float | None,
) -> str | None:
    osm_ref = osm_ref if osm_ref and OSM_REF.match(osm_ref) else None
    located = lat is not None and lon is not None
    osm_tried = False
    if osm_ref and (not located or (place and fold(name) == fold(place))):
        osm_tried = True
        entity = await _osm_entity(client, osm_ref)
        if entity and (file := await _entity_image(client, entity)):
            return file
    if located:
        for words in phrases(name, place):
            entity = await _near_entity(client, words, lat, lon)
            if entity and (file := await _entity_image(client, entity)):
                return file
    if osm_ref and not osm_tried:
        entity = await _osm_entity(client, osm_ref)
        if entity and (file := await _entity_image(client, entity)):
            return file
    if located:
        for words in phrases(name, place):
            if file := await _near_file(client, words, lat, lon):
                return file
    for words in phrases(name, place):
        entity = await _named_entity(client, words)
        if entity and (file := await _entity_image(client, entity)):
            return file
    if located:
        return await _around_file(client, lat, lon)
    return None


async def fetch(client: httpx.AsyncClient, file: str) -> Photo | None:
    payload = await _json(
        client,
        COMMONS,
        {
            "action": "query",
            "format": "json",
            "titles": f"File:{file}",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": WIDTH,
        },
    )
    pages = list(((payload.get("query") or {}).get("pages") or {}).values())
    info = ((pages[0].get("imageinfo") or [{}])[0]) if pages else {}
    address = info.get("thumburl") or info.get("url")
    if not address:
        return None
    url = httpx.URL(address)
    if url.host not in UPLOADS or url.scheme != "https":
        return None
    try:
        response = await client.get(
            url, headers={"user-agent": USER_AGENT}, timeout=timeout(), follow_redirects=False
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SourceFailed(f"la foto no llegó: {type(error).__name__}") from error
    body = response.content
    kind = image_type(body)
    if kind is None or len(body) > MAX_BYTES:
        return None
    meta = info.get("extmetadata") or {}
    return Photo(
        content=body,
        type=kind,
        author=plain((meta.get("Artist") or {}).get("value")),
        license=plain((meta.get("LicenseShortName") or {}).get("value")),
        page=str(info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/File:{file}"),
    )


async def photo(
    client: httpx.AsyncClient,
    name: str,
    place: str | None = None,
    osm_ref: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> Photo | None:
    file = await find_file(client, name, place, osm_ref, lat, lon)
    return await fetch(client, file) if file else None


SOURCES = (
    Provider(
        id="wikimedia",
        name="Wikimedia",
        category="places",
        description="A photo of a place, from Wikidata and Wikimedia Commons, "
        "with its author and licence: for the getaways and trips in "
        "Outings that have none. No key: it connects by itself the "
        "first time.",
        capabilities=("lookup",),
        serves=("places.photo",),
        available=True,
        single=True,
    ),
)
