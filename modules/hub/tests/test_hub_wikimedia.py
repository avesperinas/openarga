from __future__ import annotations

import base64
import secrets

import httpx
import pytest

from hub import capabilities
from hub.providers import wikimedia

TOKEN = secrets.token_hex(16)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 4000
THUMB = "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Sitio.jpg/1600px-Sitio.jpg"


class Sources:
    def __init__(self) -> None:
        self.asked: list[httpx.URL] = []
        self.osm_entity: str | None = "Q1"
        self.near_entity: str | None = "Q2"
        self.near_file: str | None = "Commons cerca.jpg"
        self.named: tuple[str, str] | None = ("Q3", "Vía Verde del Sitio")
        self.around: list[str] = ["Mapa.svg", "Alrededor.jpg"]
        self.image_address = THUMB
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request.url)
        if self.down:
            raise httpx.ConnectError("sin red", request=request)
        url, params = request.url, request.url.params
        if url.host == "www.openstreetmap.org":
            tags = {"name": "Sitio"} | ({"wikidata": self.osm_entity} if self.osm_entity else {})
            return httpx.Response(200, json={"elements": [{"type": "node", "tags": tags}]})
        if url.host == "www.wikidata.org" and "-haswbstatement:P625" in params.get("srsearch", ""):
            hits = [{"title": self.named[0]}] if self.named else []
            return httpx.Response(200, json={"query": {"search": hits}})
        if url.host == "www.wikidata.org" and params.get("action") == "wbgetentities":
            entity, label = self.named
            labels = {"es": {"value": label}}
            return httpx.Response(200, json={"entities": {entity: {"labels": labels}}})
        if url.host == "www.wikidata.org" and params.get("list") == "search":
            hits = [{"title": self.near_entity}] if self.near_entity else []
            return httpx.Response(200, json={"query": {"search": hits}})
        if url.host == "www.wikidata.org" and params.get("action") == "wbgetclaims":
            image = {"Q1": "De OSM.jpg", "Q2": "Cerca.jpg", "Q3": "Con nombre.jpg"}.get(
                params["entity"]
            )
            claims = [{"mainsnak": {"datavalue": {"value": image}}}] if image else []
            return httpx.Response(200, json={"claims": {"P18": claims}})
        if url.host == "commons.wikimedia.org" and params.get("list") == "geosearch":
            hits = [{"title": f"File:{one}"} for one in self.around]
            return httpx.Response(200, json={"query": {"geosearch": hits}})
        if url.host == "commons.wikimedia.org" and params.get("list") == "search":
            hits = [{"title": f"File:{self.near_file}"}] if self.near_file else []
            return httpx.Response(200, json={"query": {"search": hits}})
        if url.host == "commons.wikimedia.org" and params.get("prop") == "imageinfo":
            info = {
                "thumburl": self.image_address,
                "descriptionurl": f"https://commons.wikimedia.org/wiki/{params['titles']}",
                "extmetadata": {
                    "Artist": {
                        "value": '<a href="//commons.wikimedia.org/wiki/User:X">Autora X</a>'
                    },
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                },
            }
            return httpx.Response(200, json={"query": {"pages": {"1": {"imageinfo": [info]}}}})
        if url.host in wikimedia.UPLOADS:
            return httpx.Response(200, content=JPEG)
        raise AssertionError(f"nadie debería pedir {request.url}")

    def searched(self, host: str) -> list[str]:
        return [
            u.params["srsearch"] for u in self.asked if u.host == host and "srsearch" in u.params
        ]


@pytest.fixture
def sources(monkeypatch) -> Sources:
    fake = Sources()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    return fake


def ask(api, body: dict):
    return api.post(
        "/capabilities/places.photo",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "outings"},
    )


GETAWAY = {
    "name": "La cascada de Xorroxin",
    "place": "Erratzu",
    "osm_ref": "node/920937119",
    "lat": 43.18,
    "lon": -1.45,
}


def test_what_a_wish_names_is_searched_without_the_filler() -> None:
    assert wikimedia.phrases("Las aves de la laguna de Pitillas", "Laguna de Pitillas") == [
        "aves laguna Pitillas",
        "Laguna de Pitillas",
    ]
    assert wikimedia.phrases("Getaria: txakoli y rodaballo a la parrilla", "Guetaria") == [
        "Getaria",
        "txakoli",
        "rodaballo parrilla",
        "Guetaria",
    ]


async def test_what_the_wish_names_is_looked_for_near_its_place(api, sources) -> None:
    answer = (await ask(api, GETAWAY)).json()

    photo = answer["photo"]
    assert base64.b64decode(photo["content"]) == JPEG
    assert (photo["type"], photo["author"], photo["license"]) == (
        "image/jpeg",
        "Autora X",
        "CC BY-SA 4.0",
    )
    assert photo["page"] == "https://commons.wikimedia.org/wiki/File:Cerca.jpg"
    [searched] = sources.searched("www.wikidata.org")
    assert searched == "cascada Xorroxin haswbstatement:P18 nearcoord:20km,43.18,-1.45"
    assert not [u for u in sources.asked if u.host == "www.openstreetmap.org"]


async def test_a_wish_named_as_its_place_takes_the_image_osm_links(api, sources) -> None:
    body = GETAWAY | {"name": "Sos del Rey Católico", "place": "Sos del Rey Católico"}

    answer = (await ask(api, body)).json()

    assert answer["photo"]["page"].endswith("File:De OSM.jpg")
    assert sources.searched("www.wikidata.org") == []


async def test_without_an_entity_a_photo_taken_nearby(api, sources) -> None:
    sources.osm_entity = sources.near_entity = None

    nearby = (await ask(api, GETAWAY)).json()

    assert nearby["photo"]["page"].endswith("File:Commons cerca.jpg")
    assert "nearcoord:10km,43.18,-1.45" in sources.searched("commons.wikimedia.org")[0]


async def test_an_entity_without_coordinates_only_with_exactly_that_name(api, sources) -> None:
    sources.osm_entity = sources.near_entity = sources.near_file = None
    body = GETAWAY | {"name": "La vía verde del Sitio en bici", "place": "Vía Verde del Sitio"}

    named = (await ask(api, body)).json()
    sources.named = ("Q3", "Vía Verde de Otro Sitio")
    other = (await ask(api, body)).json()

    assert named["photo"]["page"].endswith("File:Con nombre.jpg")
    assert not other["photo"]["page"].endswith("File:Con nombre.jpg")


async def test_last_the_closest_photo_and_with_nothing_around_none(api, sources) -> None:
    sources.osm_entity = sources.near_entity = sources.near_file = sources.named = None

    around = (await ask(api, GETAWAY)).json()
    sources.around = []
    nothing = (await ask(api, GETAWAY)).json()

    assert around["photo"]["page"].endswith("File:Alrededor.jpg")
    [asked] = [u for u in sources.asked if u.params.get("list") == "geosearch"][:1]
    assert (asked.params["gscoord"], asked.params["gsradius"]) == ("43.18|-1.45", "3000")
    assert nothing == {"photo": None, "failed": None}


async def test_an_image_is_only_downloaded_from_wikimedia(api, sources) -> None:
    sources.image_address = "https://otro-sitio.example/foto.jpg"

    answer = (await ask(api, GETAWAY)).json()

    assert answer == {"photo": None, "failed": None}
    assert not [u for u in sources.asked if u.host == "otro-sitio.example"]


async def test_a_source_down_is_said_and_shows_in_its_ficha(api, sources) -> None:
    sources.down = True

    answer = (await ask(api, GETAWAY)).json()

    assert answer == {"photo": None, "failed": "Wikimedia did not answer: ConnectError"}
    [connection] = [c for c in (await api.get("/connections")).json()]
    assert connection["provider"] == "wikimedia"
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    assert [(r["operation"], r["outcome"]) for r in ficha["runs"]] == [("search", "error")]
