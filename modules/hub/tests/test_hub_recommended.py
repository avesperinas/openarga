from __future__ import annotations

import secrets

import httpx
import pytest

from hub import capabilities

TOKEN = secrets.token_hex(16)

EPISODES = {
    "results": [
        {
            "trackId": 11,
            "collectionId": 1,
            "trackName": "La caída de Constantinopla",
            "collectionName": "Un podcast sintético",
            "trackViewUrl": "https://podcasts.apple.com/es/podcast/x/id1?i=11",
            "collectionViewUrl": "https://podcasts.apple.com/es/podcast/x/id1",
            "trackTimeMillis": 3_540_000,
            "releaseDate": "2024-03-01T10:00:00Z",
        }
    ]
}
SHOWS = {
    "results": [
        {
            "collectionId": 2,
            "collectionName": "Otro podcast sintético",
            "artistName": "Una autora",
            "collectionViewUrl": "http://insecure.example/x",
            "trackCount": 40,
        }
    ]
}


def claim(value) -> dict:
    return {"mainsnak": {"datavalue": {"value": value}}}


ENTITIES = {
    "entities": {
        "Q100": {
            "id": "Q100",
            "labels": {"es": {"value": "Una película sintética"}},
            "claims": {
                "P31": [claim({"id": "Q11424"})],
                "P577": [claim({"time": "+2009-10-09T00:00:00Z"})],
                "P57": [claim({"id": "Q900"})],
                "P2047": [claim({"amount": "+127"})],
            },
            "sitelinks": {"eswiki": {"title": "Una película sintética"}},
        },
        "Q200": {
            "id": "Q200",
            "labels": {"es": {"value": "Una novela con el mismo nombre"}},
            "claims": {"P31": [claim({"id": "Q7725634"})]},
            "sitelinks": {},
        },
        "Q300": {
            "id": "Q300",
            "labels": {"en": {"value": "A synthetic series"}},
            "claims": {"P31": [claim({"id": "Q5398426"})], "P2437": [claim({"amount": "+3"})]},
            "sitelinks": {"enwiki": {"title": "A synthetic series"}},
        },
    }
}
PEOPLE = {"entities": {"Q900": {"labels": {"es": {"value": "Una directora"}}}}}


class Sources:
    def __init__(self) -> None:
        self.asked: list[httpx.URL] = []
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request.url)
        if self.down:
            raise httpx.ConnectError("sin red", request=request)
        assert request.headers["user-agent"].startswith("OpenArga")
        if request.url.host == "itunes.apple.com":
            if request.url.params["entity"] == "podcastEpisode":
                if request.url.params["country"] == "es":
                    return httpx.Response(200, json={"results": []})
                return httpx.Response(200, json=EPISODES)
            return httpx.Response(200, json=SHOWS)
        if request.url.host == "www.wikidata.org":
            action = request.url.params["action"]
            if action == "wbsearchentities":
                return httpx.Response(
                    200, json={"search": [{"id": "Q100"}, {"id": "Q200"}, {"id": "Q300"}]}
                )
            if request.url.params["props"] == "labels":
                return httpx.Response(200, json=PEOPLE)
            return httpx.Response(200, json=ENTITIES)
        raise AssertionError(f"nadie debería pedir {request.url}")


@pytest.fixture
def sources(monkeypatch) -> Sources:
    fake = Sources()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    return fake


def ask(api, capability: str, body: dict):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "insights"},
    )


async def test_an_episode_is_looked_for_in_spain_and_then_in_the_us(api, sources) -> None:
    answer = (
        await ask(api, "podcasts.search", {"query": "constantinopla", "kind": "episode"})
    ).json()

    [found] = answer["candidates"]
    assert found["title"] == "La caída de Constantinopla"
    assert found["show"] == "Un podcast sintético"
    assert found["minutes"] == 59 and found["year"] == 2024 and found["store"] == "us"
    assert found["url"] == "https://podcasts.apple.com/es/podcast/x/id1?i=11"
    assert [url.params["country"] for url in sources.asked] == ["es", "us"]
    connected = {c["provider"] for c in (await api.get("/connections")).json()}
    assert connected == {"apple_podcasts"}


async def test_a_show_without_https_comes_without_link(api, sources) -> None:
    answer = (await ask(api, "podcasts.search", {"query": "otro", "kind": "podcast"})).json()

    [found] = answer["candidates"]
    assert (found["title"], found["show"], found["episodes"]) == (
        "Otro podcast sintético",
        "Una autora",
        40,
    )
    assert found["url"] is None


async def test_only_films_come_from_wikidata_with_who_made_them(api, sources) -> None:
    films = (await ask(api, "films.search", {"query": "sintética", "kind": "film"})).json()
    series = (await ask(api, "films.search", {"query": "sintética", "kind": "series"})).json()

    [film] = films["candidates"]
    assert film == {
        "id": "Q100",
        "title": "Una película sintética",
        "year": 2009,
        "creators": ["Una directora"],
        "minutes": 127,
        "seasons": None,
        "wikipedia": "https://es.wikipedia.org/wiki/Una_pel%C3%ADcula_sint%C3%A9tica",
    }
    assert [one["title"] for one in series["candidates"]] == ["A synthetic series"]
    assert series["candidates"][0]["seasons"] == 3


async def test_a_source_that_is_down_says_so_and_shows_in_its_card(api, sources) -> None:
    sources.down = True

    answer = (await ask(api, "films.search", {"query": "x"})).json()

    assert answer["candidates"] == [] and "Wikidata no contesta" in answer["failed"]
    connected = {c["provider"]: c for c in (await api.get("/connections")).json()}
    card = (await api.get(f"/connections/{connected['wikidata']['id']}")).json()
    assert [(r["operation"], r["outcome"]) for r in card["runs"]] == [("search", "error")]
