from __future__ import annotations

import secrets
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import text

from hub import capabilities
from hub.providers import nearby

TOKEN = secrets.token_hex(16)
HOTEL = {"lat": 35.0037, "lon": 135.7788}
ELEMENTS = [
    {
        "type": "way",
        "id": 1,
        "center": {"lat": 35.0050, "lon": 135.7790},
        "tags": {"name": "何必館", "name:en": "Kahitsukan", "tourism": "museum"},
    },
    {
        "type": "node",
        "id": 2,
        "lat": 35.0040,
        "lon": 135.7789,
        "tags": {"name": "八坂神社", "name:es": "Santuario Yasaka", "amenity": "place_of_worship"},
    },
    {
        "type": "way",
        "id": 3,
        "center": {"lat": 35.0041, "lon": 135.7790},
        "tags": {"name": "八坂神社", "name:es": "Santuario Yasaka", "historic": "church"},
    },
    {"type": "node", "id": 4, "tags": {"name": "Roto", "tourism": "museum"}},
]


class Overpass:
    def __init__(self) -> None:
        self.status = 200
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, json={"elements": ELEMENTS})


@pytest.fixture
def overpass(monkeypatch) -> Overpass:
    fake = Overpass()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(nearby, "PACE", nearby._Pace())
    monkeypatch.setattr(nearby, "MIN_INTERVAL", 0.0)
    return fake


def ask(api, body: dict):
    return api.post(
        "/capabilities/places.nearby",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "travel"},
    )


async def runs(api) -> list[str]:
    listed = (await api.get("/connections")).json()
    [connection] = [c for c in listed if c["provider"] == "overpass"]
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    return [run["outcome"] for run in ficha["runs"]]


async def test_what_is_near_comes_nearest_first_once_and_in_a_name_you_read(
    api, schema, overpass
) -> None:
    async with schema.connect() as connection:
        before = await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )

    answer = (await ask(api, {**HOTEL, "kind": "sights", "radius": 800})).json()

    assert answer["failed"] is None
    names = [(p["name"], p["kind"], p["local_name"]) for p in answer["places"]]
    assert names == [
        ("Santuario Yasaka", "place_of_worship", "八坂神社"),
        ("Kahitsukan", "museum", "何必館"),
    ]
    first = answer["places"][0]
    assert (first["osm_type"], first["osm_id"], first["group"]) == ("node", 2, "sights")
    assert 0 < first["distance_m"] < answer["places"][1]["distance_m"]
    assert await runs(api) == ["ok"]
    async with schema.connect() as connection:
        assert before == await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )


async def test_it_asks_only_for_that_kind_and_radius_and_not_twice(api, overpass) -> None:
    await ask(api, {**HOTEL, "kind": "food", "radius": 500})
    await ask(api, {**HOTEL, "kind": "food", "radius": 500})

    [request] = overpass.asked
    sent = parse_qs(request.content.decode())["data"][0]
    assert "around:500,35.003700,135.778800" in sent
    assert "restaurant" in sent and "museum" not in sent
    assert request.headers["user-agent"].startswith("OpenArga/")


async def test_overpass_busy_once_is_asked_again(api, overpass, monkeypatch) -> None:
    monkeypatch.setattr(nearby, "RETRY_SECONDS", 0.0)

    def busy_first(request: httpx.Request) -> httpx.Response:
        overpass.asked.append(request)
        if len(overpass.asked) == 1:
            return httpx.Response(504)
        return httpx.Response(200, json={"elements": ELEMENTS})

    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(busy_first))
    answer = (await ask(api, {**HOTEL, "kind": "nature"})).json()

    assert len(overpass.asked) == 2
    assert answer["failed"] is None and len(answer["places"]) == 2


async def test_overpass_still_busy_is_said_and_seen(api, overpass, monkeypatch) -> None:
    monkeypatch.setattr(nearby, "RETRY_SECONDS", 0.0)
    overpass.status = 429

    answer = (await ask(api, {**HOTEL, "kind": "nature"})).json()

    assert answer["places"] == [] and "saturada" in answer["failed"]
    assert len(overpass.asked) == 2
    assert await runs(api) == ["error"]


async def test_a_radius_too_big_is_refused(api, overpass) -> None:
    assert (await ask(api, {**HOTEL, "radius": 20000})).status_code == 422
