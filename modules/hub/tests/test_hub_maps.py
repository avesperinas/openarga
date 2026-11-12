from __future__ import annotations

import base64
import gzip
import secrets
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text

from hub import capabilities, worker
from hub.providers import maps, routes

TOKEN = secrets.token_hex(16)
REGION = Path(__file__).resolve().parents[2] / "outings/ui/public/map/pamplona/region.pmtiles"
PAMPLONA = {"z": 9, "x": 253, "y": 188}
PAMPLONA_BYTES = 344_760


class Protomaps:
    def __init__(self) -> None:
        self.data = REGION.read_bytes()
        self.builds = ["20261001.pmtiles"]
        self.builds_status = 200
        self.gone: set[str] = set()
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if request.url.host == "build-metadata.protomaps.dev":
            if self.builds_status != 200:
                return httpx.Response(self.builds_status)
            return httpx.Response(200, json=[{"key": key} for key in self.builds])
        if request.url.path.lstrip("/") in self.gone:
            return httpx.Response(404)
        first, last = request.headers["range"].split("=")[1].split("-")
        return httpx.Response(206, content=self.data[int(first) : int(last) + 1])


class Osrm:
    def __init__(self) -> None:
        self.code = "Ok"
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if self.code != "Ok":
            return httpx.Response(400, json={"code": self.code})
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "distance": 1996.7,
                        "duration": 1610.2,
                        "legs": [
                            {"distance": 900.4, "duration": 700.1},
                            {"distance": 1096.3, "duration": 910.1},
                        ],
                        "geometry": {"coordinates": [[-1.64, 42.81], [-1.65, 42.81]]},
                    }
                ],
            },
        )


@pytest.fixture
def sources(monkeypatch):
    protomaps, osrm = Protomaps(), Osrm()

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.host == "routing.openstreetmap.de":
            return osrm(request)
        return protomaps(request)

    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(route))
    monkeypatch.setattr(maps, "ARCHIVE", maps._Archive())
    monkeypatch.setattr(routes, "CACHE", {})
    monkeypatch.setattr(capabilities, "_tile_noted", {"at": None})
    monkeypatch.setattr(capabilities, "time", SimpleNamespace(monotonic=lambda: 5.0))
    return protomaps, osrm


def ask(api, capability: str, body: dict):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "travel"},
    )


async def runs(api, provider: str) -> list[str]:
    listed = (await api.get("/connections")).json()
    [connection] = [c for c in listed if c["provider"] == provider]
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    return [run["outcome"] for run in ficha["runs"]]


def test_the_tile_number_is_the_one_of_the_format() -> None:
    assert [maps.tile_id(0, 0, 0)] == [0]
    assert [maps.tile_id(1, x, y) for x, y in ((0, 0), (0, 1), (1, 1), (1, 0))] == [1, 2, 3, 4]
    assert maps.tile_id(2, 0, 0) == 5


async def test_a_tile_is_the_one_in_the_file_and_the_second_does_not_go_out(
    api, schema, sources
) -> None:
    protomaps, _ = sources
    async with schema.connect() as connection:
        logged = await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )

    first = (await ask(api, "maps.tile", PAMPLONA)).json()
    asked = len(protomaps.asked)
    again = (await ask(api, "maps.tile", PAMPLONA)).json()

    raw = base64.b64decode(first["tile"])
    assert (first["failed"], first["build"]) == (None, "20261001.pmtiles")
    assert len(raw) == PAMPLONA_BYTES
    assert raw[:2] != b"\x1f\x8b"
    with pytest.raises(gzip.BadGzipFile):
        gzip.decompress(raw)
    assert again["tile"] == first["tile"]
    assert len(protomaps.asked) == asked
    assert await runs(api, "protomaps") == ["ok"]
    async with schema.connect() as connection:
        assert logged == await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )


async def test_where_there_is_nothing_the_tile_is_null(api, sources) -> None:
    answer = (await ask(api, "maps.tile", {"z": 9, "x": 100, "y": 100})).json()

    assert (answer["tile"], answer["failed"]) == (None, None)


async def test_a_tile_that_does_not_exist_is_refused(api, sources) -> None:
    answer = await ask(api, "maps.tile", {"z": 2, "x": 4, "y": 0})

    assert answer.status_code == 422


async def test_a_map_version_that_disappears_is_said_and_the_next_is_chosen(api, sources) -> None:
    protomaps, _ = sources
    await ask(api, "maps.tile", PAMPLONA)
    protomaps.gone.add("20261001.pmtiles")
    protomaps.builds.append("20261002.pmtiles")

    gone = (await ask(api, "maps.tile", {"z": 9, "x": 252, "y": 188})).json()
    back = (await ask(api, "maps.tile", {"z": 9, "x": 252, "y": 188})).json()

    assert gone["tile"] is None and "ya no está" in gone["failed"]
    assert (back["failed"], back["build"]) == (None, "20261002.pmtiles")
    assert back["tile"] is not None
    assert await runs(api, "protomaps") == ["ok", "error", "ok"]


def builds_asked(protomaps: Protomaps) -> int:
    return sum(1 for one in protomaps.asked if one.url.host == "build-metadata.protomaps.dev")


async def test_without_the_list_of_maps_it_says_why_and_does_not_ask_again(api, sources) -> None:
    protomaps, _ = sources
    protomaps.builds_status = 403

    first = (await ask(api, "maps.tile", PAMPLONA)).json()
    second = (await ask(api, "maps.tile", {"z": 9, "x": 252, "y": 188})).json()

    assert first["tile"] is None
    assert first["failed"] == "Protomaps no dijo cuál es su mapa más reciente: contestó 403"
    assert second["failed"] == first["failed"]
    assert builds_asked(protomaps) == 1
    assert await runs(api, "protomaps") == ["error", "error"]

    protomaps.builds_status = 200
    maps.ARCHIVE.refused = None
    back = (await ask(api, "maps.tile", PAMPLONA)).json()

    assert (back["failed"], back["build"]) == (None, "20261001.pmtiles")
    assert await runs(api, "protomaps") == ["ok", "error", "error"]


async def test_a_day_without_the_list_of_maps_keeps_the_one_in_use(api, sources) -> None:
    protomaps, _ = sources
    await ask(api, "maps.tile", PAMPLONA)
    protomaps.builds_status = 503
    maps.ARCHIVE.chosen_at -= maps.BUILD_SECONDS + 1

    west = (await ask(api, "maps.tile", {"z": 9, "x": 252, "y": 188})).json()
    south = (await ask(api, "maps.tile", {"z": 9, "x": 253, "y": 189})).json()

    assert (west["failed"], west["build"]) == (None, "20261001.pmtiles")
    assert west["tile"] is not None
    assert south["failed"] is None
    assert builds_asked(protomaps) == 2
    assert await runs(api, "protomaps") == ["ok"]


async def worker_tick(monkeypatch, protomaps: Protomaps, person: UUID) -> dict:
    async def nothing(*_):
        return None

    async def nobody_due(*_):
        return []

    async def everyone() -> list[UUID]:
        return [person]

    monkeypatch.setattr(worker, "runnable", nobody_due)
    monkeypatch.setattr(worker.avisos, "refresh", nothing)
    monkeypatch.setattr(worker, "beat", lambda: None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(protomaps)) as source:
        return await worker.tick(
            datetime.now(UTC), False, people=everyone, source=source, kernel=None
        )  # type: ignore[arg-type]


async def an_hour_ago(schema) -> None:
    async with schema.begin() as connection:
        await connection.execute(
            text("update hub.hub_run set started_at = started_at - interval '61 min'")
        )


async def test_a_red_map_goes_back_to_green_without_anyone_asking_for_a_tile(
    api, schema, sources, monkeypatch, person
) -> None:
    protomaps, _ = sources
    protomaps.builds_status = 503
    await ask(api, "maps.tile", PAMPLONA)
    maps.ARCHIVE.refused = None
    await ask(api, "maps.tile", PAMPLONA)
    protomaps.builds_status = 200
    maps.ARCHIVE.refused = None
    asked = len(protomaps.asked)

    assert await worker_tick(monkeypatch, protomaps, person) == {}
    assert len(protomaps.asked) == asked

    await an_hour_ago(schema)
    done = await worker_tick(monkeypatch, protomaps, person)
    again = await worker_tick(monkeypatch, protomaps, person)

    assert done == {str(person): {"Protomaps": "ok"}}
    assert again == {}
    assert await runs(api, "protomaps") == ["ok", "error", "error"]
    [listed] = [c for c in (await api.get("/connections")).json() if c["provider"] == "protomaps"]
    assert listed["state"] == "active"


async def test_a_red_map_that_still_fails_says_why(
    api, schema, sources, monkeypatch, person
) -> None:
    protomaps, _ = sources
    protomaps.builds_status = 403
    await ask(api, "maps.tile", PAMPLONA)
    await an_hour_ago(schema)
    maps.ARCHIVE.refused = None

    done = await worker_tick(monkeypatch, protomaps, person)

    assert done == {str(person): {"Protomaps": "error"}}
    listed = (await api.get("/connections")).json()
    [connection] = [c for c in listed if c["provider"] == "protomaps"]
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    assert [run["detail"] for run in ficha["runs"]][0] == (
        "Protomaps no dijo cuál es su mapa más reciente: contestó 403"
    )


async def test_a_route_brings_its_line_and_each_leg_and_asks_once(api, sources) -> None:
    _, osrm = sources
    body = {"profile": "foot", "points": [[-1.6436, 42.8169], [-1.651, 42.8125], [-1.64, 42.81]]}

    answer = (await ask(api, "routes.directions", body)).json()
    again = (await ask(api, "routes.directions", body)).json()

    route = answer["route"]
    assert (route["distance_m"], route["duration_s"]) == (1997, 1610)
    assert [leg["distance_m"] for leg in route["legs"]] == [900, 1096]
    assert route["geometry"][0] == [-1.64, 42.81]
    assert again == answer
    [request] = osrm.asked
    assert request.url.path.startswith("/routed-foot/route/v1/driving/-1.643600,42.816900;")
    assert request.headers["user-agent"].startswith("OpenArga/")


async def test_without_a_way_it_is_said_and_seen(api, sources) -> None:
    _, osrm = sources
    osrm.code = "NoRoute"

    answer = (await ask(api, "routes.directions", {"points": [[0, 0], [1, 1]]})).json()

    assert answer["route"] is None and "NoRoute" in answer["failed"]
    assert await runs(api, "osrm") == ["error"]
