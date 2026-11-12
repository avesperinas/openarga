from __future__ import annotations

import secrets

import httpx
import pytest
from sqlalchemy import text

from hub import capabilities
from hub.providers import places

TOKEN = secrets.token_hex(16)
BRUGES = [
    {
        "osm_type": "relation",
        "osm_id": 562654,
        "lat": "51.2085526",
        "lon": "3.2267720",
        "addresstype": "city",
        "name": "Brujas",
        "display_name": "Brujas, Flandes Occidental, Flandes, Bélgica",
        "address": {
            "ISO3166-2-lvl4": "BE-VLG",
            "country_code": "be",
            "city": "Brujas",
            "country": "Bélgica",
        },
    },
    {"osm_type": "node", "osm_id": 1, "name": "Roto"},
]


class Nominatim:
    def __init__(self) -> None:
        self.down = False
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if self.down:
            raise httpx.ConnectError("sin red", request=request)
        return httpx.Response(200, json=BRUGES)


@pytest.fixture
def nominatim(monkeypatch) -> Nominatim:
    fake = Nominatim()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(places, "PACE", places._Pace())
    monkeypatch.setattr(places, "MIN_INTERVAL", 0.0)
    return fake


def ask(api, body: dict):
    return api.post(
        "/capabilities/places.search",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "travel"},
    )


async def logged(schema) -> int:
    async with schema.connect() as connection:
        return await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )


async def test_a_search_brings_places_and_leaves_nothing_in_the_log(api, schema, nominatim):
    before = await logged(schema)

    answer = (await ask(api, {"query": "Brujas"})).json()

    assert answer["failed"] == []
    [bruges] = answer["candidates"]
    assert (bruges["name"], bruges["lat"], bruges["lon"]) == ("Brujas", 51.2085526, 3.226772)
    assert (bruges["country_code"], bruges["region_code"]) == ("BE", "BE-VLG")
    assert (bruges["osm_type"], bruges["osm_id"], bruges["kind"]) == ("relation", 562654, "city")
    assert (bruges["town"], bruges["country"]) == ("Brujas", "Bélgica")
    listed = (await api.get("/connections")).json()
    [connection] = [c for c in listed if c["provider"] == "nominatim"]
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    assert [(r["operation"], r["outcome"]) for r in ficha["runs"]] == [("search", "ok")]
    assert await logged(schema) == before


async def test_it_says_who_asks_and_in_which_language(api, nominatim) -> None:
    await ask(api, {"query": "Brujas"})

    [request] = nominatim.asked
    assert request.headers["user-agent"].startswith("OpenArga/")
    assert request.url.params["accept-language"] == "es"
    assert request.url.params["q"] == "Brujas"


async def test_the_same_search_twice_asks_once(api, nominatim) -> None:
    await ask(api, {"query": "Brujas"})
    again = (await ask(api, {"query": "  brujas "})).json()

    assert len(nominatim.asked) == 1
    assert [one["name"] for one in again["candidates"]] == ["Brujas"]


async def test_nominatim_down_is_said_and_seen(api, nominatim) -> None:
    nominatim.down = True

    answer = (await ask(api, {"query": "Brujas"})).json()

    assert answer["candidates"] == []
    assert answer["failed"][0]["source"] == "nominatim"
    assert "no contestó" in answer["failed"][0]["reason"]
    listed = (await api.get("/connections")).json()
    [connection] = [c for c in listed if c["provider"] == "nominatim"]
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    assert [r["outcome"] for r in ficha["runs"]] == ["error"]


async def test_one_request_per_second_across_the_process(monkeypatch) -> None:
    import time

    monkeypatch.setattr(places, "PACE", places._Pace())
    monkeypatch.setattr(places, "MIN_INTERVAL", 0.2)
    moments: list[float] = []

    def answer(request: httpx.Request) -> httpx.Response:
        moments.append(time.monotonic())
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        import asyncio

        await asyncio.gather(*(places.search(client, name) for name in ("a b", "c d", "e f")))

    gaps = [later - earlier for earlier, later in zip(moments, moments[1:], strict=False)]
    assert len(moments) == 3
    assert all(gap >= 0.19 for gap in gaps)
