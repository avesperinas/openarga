from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_tenancy import USER_HEADER
from planner import hub

CONNECTION = str(uuid4())
MODULES = Path(__file__).resolve().parents[2]
TOKEN = secrets.token_hex(16)


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, person):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        c.headers[USER_HEADER] = str(person)
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    await kernel_db.engine().dispose()


class Hub:
    def __init__(self, kernel: AsyncClient, connection: str = CONNECTION) -> None:
        self.kernel = kernel
        self.connection = connection
        self.passes = 0

    async def post(self, kind: str, payload: dict, dedup: str) -> None:
        response = await self.kernel.post(
            "/events",
            json={
                "ts": datetime.now(UTC).isoformat(),
                "module": "hub",
                "source": "ical",
                "type": kind,
                "payload": payload,
                "dedup_hash": dedup,
            },
        )
        assert response.status_code in (200, 201), response.text

    async def run(self, events: dict[str, dict], label: str = "Equipo de prueba") -> None:
        self.passes += 1
        prints = {}
        for uid, body in events.items():
            fingerprint = f"{hash(tuple(sorted(body.items()))) & 0xFFFFFFFF:08x}"
            prints[uid] = fingerprint
            await self.post(
                "calendar.event",
                {"connection": self.connection, "uid": uid, "fingerprint": fingerprint, **body},
                f"calendar:{self.connection}:{uid}:{fingerprint}",
            )
        await self.post(
            "calendar.feed",
            {"connection": self.connection, "provider": "ical", "label": label, "events": prints},
            f"feed:{self.connection}:{self.passes}",
        )
        await self.post(
            "hub.run",
            {
                "connection": self.connection,
                "provider": "ical",
                "label": label,
                "outcome": "ok",
                "detail": None,
            },
            f"run:{self.connection}:{self.passes}",
        )

    async def fail(self, detail: str) -> None:
        self.passes += 1
        await self.post(
            "hub.run",
            {
                "connection": self.connection,
                "provider": "ical",
                "label": "x",
                "outcome": "error",
                "detail": detail,
            },
            f"run:{self.connection}:{self.passes}",
        )

    async def removed(self) -> None:
        await self.post(
            "hub.connection",
            {
                "connection": self.connection,
                "provider": "ical",
                "label": "x",
                "state": "removed",
                "removed": True,
                "paused": False,
            },
            f"connection:{self.connection}:removed",
        )


MATCH = {
    "title": "Partido de prueba",
    "all_day": False,
    "start": "2026-10-11T16:30:00+00:00",
    "end": "2026-10-11T18:30:00+00:00",
    "tz": "UTC",
    "location": "Estadio de prueba",
    "description": None,
    "url": None,
    "status": "confirmed",
}
HOLIDAY = {
    "title": "Fiesta de prueba",
    "all_day": True,
    "start": "2026-10-12",
    "end": "2026-10-13",
    "tz": "UTC",
    "location": None,
    "description": None,
    "url": None,
    "status": "confirmed",
}
WEEK = {"from": "2026-10-05T00:00:00+02:00", "to": "2026-10-19T00:00:00+02:00"}


async def layers(api) -> list[dict]:
    response = await api.get("/calendars")
    assert response.status_code == 200, response.text
    return response.json()


async def shown(api) -> dict[str, dict]:
    response = await api.get("/occurrences", params=WEEK)
    assert response.status_code == 200, response.text
    return {one["title"]: one for one in response.json()}


async def test_a_connection_made_in_hub_brings_its_own_layer(api, kernel) -> None:
    await Hub(kernel).run({"m1": MATCH, "h1": HOLIDAY})

    [layer] = [one for one in await layers(api) if one["origin"] == "subscription"]
    assert (layer["name"], layer["connection_id"]) == ("Equipo de prueba", CONNECTION)
    assert layer["subscription"]["updated_at"] is not None
    assert layer["subscription"]["failing"] is False
    found = await shown(api)
    assert found["Partido de prueba"]["calendar_id"] == layer["id"]
    assert found["Partido de prueba"]["location"] == "Estadio de prueba"
    assert found["Fiesta de prueba"]["all_day"] is True


async def test_plugged_in_hub_the_layer_takes_what_was_answered_to_planner(api, kernel) -> None:
    source = Hub(kernel)
    await source.post(
        "hub.connection",
        {
            "connection": CONNECTION,
            "provider": "ical",
            "label": "Pruebas",
            "state": "active",
            "removed": False,
            "paused": False,
            "produces": ["calendar.event", "calendar.feed"],
            "plugs": {"planner.calendar": {"name": "Mi calendario", "tone": 7}},
        },
        f"connection:{CONNECTION}:plugged",
    )
    await source.run({"m1": MATCH})

    [layer] = [one for one in await layers(api) if one["origin"] == "subscription"]
    assert (layer["name"], layer["tone"]) == ("Mi calendario", 7)


async def test_what_changes_changes_and_what_goes_away_goes_away(api, kernel) -> None:
    source = Hub(kernel)
    await source.run({"m1": MATCH, "h1": HOLIDAY})
    await layers(api)

    moved = {**MATCH, "start": "2026-10-11T19:00:00+00:00", "end": "2026-10-11T21:00:00+00:00"}
    await source.run({"m1": moved})
    await layers(api)

    found = await shown(api)
    assert found["Partido de prueba"]["start"] == "2026-10-11T19:00:00+00:00"
    assert "Fiesta de prueba" not in found


async def test_the_version_the_last_feed_names_is_the_good_one(api, kernel) -> None:
    source = Hub(kernel)
    moved = {**MATCH, "start": "2026-10-11T19:00:00+00:00", "end": "2026-10-11T21:00:00+00:00"}
    await source.run({"m1": MATCH})
    await source.run({"m1": moved})
    await layers(api)
    await source.run({"m1": MATCH})
    await layers(api)

    assert (await shown(api))["Partido de prueba"]["start"] == "2026-10-11T16:30:00+00:00"


async def test_a_failing_pass_is_said_and_empties_nothing(api, kernel) -> None:
    source = Hub(kernel)
    await source.run({"m1": MATCH})
    await source.fail("el servidor del calendario falla (503)")

    [layer] = [one for one in await layers(api) if one["origin"] == "subscription"]
    assert layer["subscription"]["failing"] is True
    assert layer["subscription"]["detail"] == "el servidor del calendario falla (503)"
    assert layer["subscription"]["updated_at"] is not None
    assert "Partido de prueba" in await shown(api)


async def test_removed_in_hub_it_stops_showing(api, kernel) -> None:
    source = Hub(kernel)
    await source.run({"m1": MATCH})
    await layers(api)

    await source.removed()

    assert [one for one in await layers(api) if one["origin"] == "subscription"] == []
    assert "Partido de prueba" not in await shown(api)


async def test_what_is_subscribed_is_not_edited_but_can_be_hidden(api, kernel) -> None:
    await Hub(kernel).run({"m1": MATCH, "h1": HOLIDAY})
    await layers(api)
    match = (await shown(api))["Partido de prueba"]

    edit = await api.patch(
        f"/events/{match['event_id']}", json={"changes": {"title": "Otro"}, "scope": "all"}
    )
    assert edit.status_code == 422
    assert "no se edita" in edit.json()["detail"]

    hidden = await api.post(f"/feed/{match['id'].removeprefix('feed:')}/hide")
    assert hidden.status_code == 204
    found = await shown(api)
    assert "Partido de prueba" not in found
    assert "Fiesta de prueba" in found


async def test_a_hidden_layer_hides_what_it_brings_from_the_widget(api, kernel) -> None:
    await Hub(kernel).run({"m1": MATCH})
    [layer] = [one for one in await layers(api) if one["origin"] == "subscription"]

    only_own = await api.get(
        "/occurrences",
        params={
            **WEEK,
            "calendars": [one["id"] for one in await layers(api) if one["origin"] == "own"],
        },
    )
    assert "Partido de prueba" not in {one["title"] for one in only_own.json()}
    only_it = await api.get("/occurrences", params={**WEEK, "calendars": [layer["id"]]})
    assert [one["title"] for one in only_it.json()] == ["Partido de prueba"]


async def test_search_finds_what_is_subscribed(api, kernel) -> None:
    await Hub(kernel).run({"m1": MATCH})
    await layers(api)

    found = (await api.get("/search", params={"q": "estadio"})).json()

    assert [one["title"] for one in found] == ["Partido de prueba"]


async def test_nobody_else_sees_it(api, kernel) -> None:
    other = "00000000-0000-4000-8000-00000000b0b0"

    await Hub(kernel).run({"m1": MATCH})
    await layers(api)

    response = await api.get("/occurrences", params=WEEK, headers={USER_HEADER: other})
    assert "Partido de prueba" not in {one["title"] for one in response.json()}


@pytest.fixture
async def hub_app(kernel, schema, monkeypatch):
    from arga_testing import fresh_modules
    from kernel import capabilities as kernel_capabilities

    os.environ.setdefault("HUB_CREDENTIALS_KEY", os.urandom(32).hex())
    from hub import capabilities as hub_capabilities
    from hub import db as hub_db
    from hub.main import app as hub_app
    from kernel.main import app as kernel_app

    async with schema.begin() as connection:
        await fresh_modules(connection, "hub", "planner", fresh=["hub"])
    hub_db.engine.cache_clear()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(kernel_capabilities, "hub_transport", lambda: ASGITransport(app=hub_app))
    monkeypatch.setattr(hub_capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    monkeypatch.setattr(hub, "transport", lambda: ASGITransport(app=kernel_app))
    monkeypatch.setenv("KERNEL_URL", "http://kernel")
    yield hub_app
    await hub_db.engine().dispose()
    hub_db.engine.cache_clear()
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'hub'"))


async def test_subscribing_creates_the_connection_in_hub_and_its_layer_here(api, hub_app) -> None:
    response = await api.post(
        "/subscriptions",
        json={
            "provider": "holidays",
            "name": "Festivos · Navarra",
            "tone": 4,
            "params": {"country": "ES", "region": "ES-NC"},
        },
    )

    assert response.status_code == 201, response.text
    layer = response.json()
    assert (layer["name"], layer["tone"], layer["origin"]) == (
        "Festivos · Navarra",
        4,
        "subscription",
    )
    async with AsyncClient(transport=ASGITransport(app=hub_app), base_url="http://hub") as c:
        listed = (await c.get("/connections")).json()
    [found] = [one for one in listed if one["id"] == layer["connection_id"]]
    assert (found["provider"], found["category"], found["state"]) == (
        "holidays",
        "calendar",
        "active",
    )


async def test_subscribing_twice_to_the_same_gives_back_the_same_layer(api, hub_app) -> None:
    body = {
        "provider": "holidays",
        "name": "Festivos · Región",
        "tone": 4,
        "params": {"country": "ES", "region": "ES-NC"},
    }
    first = await api.post("/subscriptions", json=body)
    again = await api.post("/subscriptions", json={**body, "name": "Otro nombre", "tone": 2})

    assert first.status_code == 201, first.text
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["name"] == "Festivos · Región"
    subscribed = [one for one in await layers(api) if one["origin"] == "subscription"]
    assert len(subscribed) == 1


async def test_subscribing_to_a_team_creates_its_connection(api, hub_app) -> None:
    response = await api.post(
        "/subscriptions",
        json={
            "provider": "football",
            "name": "Equipo de prueba",
            "tone": 5,
            "params": {"team": "11", "league": "esp.1", "team_name": "Equipo de prueba"},
        },
    )

    assert response.status_code == 201, response.text
    async with AsyncClient(transport=ASGITransport(app=hub_app), base_url="http://hub") as c:
        ficha = (await c.get(f"/connections/{response.json()['connection_id']}")).json()
    assert ficha["provider"] == "football"
    assert ficha["settings"] == {"team": "11", "league": "esp.1", "team_name": "Equipo de prueba"}


async def test_a_subscription_that_makes_no_sense_is_said_by_its_parameter(api, hub_app) -> None:
    response = await api.post(
        "/subscriptions",
        json={"provider": "ical", "name": "Nada", "tone": 2, "params": {"url": "no"}},
    )

    assert response.status_code == 422
    assert "https://" in response.json()["detail"]
    assert [one for one in await layers(api) if one["origin"] == "subscription"] == []


async def test_without_the_hub_subscribing_says_so(api, kernel, monkeypatch) -> None:
    from kernel.main import app as kernel_app

    monkeypatch.setattr(hub, "transport", lambda: ASGITransport(app=kernel_app))
    monkeypatch.setenv("KERNEL_URL", "http://kernel")
    monkeypatch.delenv("MODULE_REGISTRATION_TOKEN", raising=False)

    response = await api.post(
        "/subscriptions",
        json={"provider": "formula1", "name": "F1", "tone": 3, "params": {}},
    )

    assert response.status_code in (502, 503)
    assert "Hub" in response.json()["detail"]


async def test_the_menu_comes_from_the_hub_with_what_you_already_have(api, hub_app) -> None:
    for team, name in (("11", "Equipo uno"), ("22", "Equipo dos")):
        created = await api.post(
            "/subscriptions",
            json={
                "provider": "football",
                "name": name,
                "tone": 2,
                "params": {"team": team, "league": "esp.1", "team_name": name},
            },
        )
        assert created.status_code == 201, created.text

    menu = (await api.get("/subscriptions/catalogue")).json()

    sources = {one["provider"]: one for one in menu["sources"]}
    assert {"holidays", "formula1", "football", "ical"} <= set(sources)
    assert sorted(one["name"] for one in sources["football"]["subscribed"]) == [
        "Equipo dos",
        "Equipo uno",
    ]
    assert sources["formula1"]["subscribed"] == []
    assert sources["football"]["asks"][0]["source"] == "teams"
    assert {group["id"] for group in menu["groups"]} >= {"sport", "holidays", "other"}
    [inlet] = sources["football"]["inlets"]
    assert inlet["key"] == "planner.calendar"
    assert [one["key"] for one in inlet["settings"]] == ["name", "tone"]


async def test_subscribing_tells_the_hub_the_name_and_tone_of_the_layer(api, hub_app) -> None:
    layer = (
        await api.post(
            "/subscriptions",
            json={"provider": "formula1", "name": "La F1", "tone": 3, "params": {}},
        )
    ).json()

    async with AsyncClient(transport=ASGITransport(app=hub_app), base_url="http://hub") as c:
        ficha = (await c.get(f"/connections/{layer['connection_id']}")).json()
    assert ficha["plugs"] == {"planner.calendar": {"name": "La F1", "tone": 3}}


async def test_what_a_source_asks_is_searched_through_the_hub(api, hub_app, monkeypatch) -> None:
    from hub import catalogue

    async def teams(_client, query, _parent):
        return [{"code": "9", "name": f"Equipo {query}", "detail": "Liga de prueba"}]

    monkeypatch.setitem(catalogue.BY_ID["football"].searches, "teams", teams)

    found = await api.get(
        "/subscriptions/search", params={"provider": "football", "ask": "team", "q": "Prueba"}
    )

    assert found.status_code == 200, found.text
    assert found.json()["results"][0]["name"] == "Equipo Prueba"


async def test_unsubscribing_from_the_menu_removes_the_connection_and_the_layer(
    api, hub_app
) -> None:
    layer = (
        await api.post(
            "/subscriptions",
            json={"provider": "formula1", "name": "Fórmula 1", "tone": 1, "params": {}},
        )
    ).json()

    removed = await api.delete(f"/subscriptions/{layer['id']}")

    assert removed.status_code == 204, removed.text
    assert layer["id"] not in [one["id"] for one in await layers(api)]
    async with AsyncClient(transport=ASGITransport(app=hub_app), base_url="http://hub") as c:
        listed = (await c.get("/connections")).json()
    assert layer["connection_id"] not in [one["id"] for one in listed]


async def test_a_layer_of_yours_is_not_unsubscribed(api, hub_app) -> None:
    own = [one for one in await layers(api) if one["origin"] == "own"][0]

    refused = await api.delete(f"/subscriptions/{own['id']}")

    assert refused.status_code == 409
