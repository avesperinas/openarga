from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import test_planner_subscriptions as subscriptions
from httpx import ASGITransport, AsyncClient

kernel = subscriptions.kernel
migrated = subscriptions.migrated
hub_app = subscriptions.hub_app

READ = {"x-arga-scopes": "planner:read"}
WRITE = {"x-arga-scopes": "planner:read planner:write"}
MADRID = ZoneInfo("Europe/Madrid")


async def call(api, name: str, arguments: dict, headers: dict = WRITE) -> dict:
    response = await api.post(f"/tools/{name}", json=arguments, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def hub_connections(app) -> list[dict]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hub") as client:
        return (await client.get("/connections")).json()


async def test_claude_makes_a_layer_of_holidays_and_work_frees_them(api) -> None:
    await api.get("/calendars")
    local = (await call(api, "create_calendar", {"name": "Festivos locales", "tone": 3}))["created"]
    assert (local["origin"], local["display"]) == ("own", "events")
    work = (
        await call(api, "create_calendar", {"name": "Trabajo", "tone": 7, "display": "background"})
    )["created"]
    soon = (datetime.now(MADRID) + timedelta(days=3)).date()
    await call(
        api,
        "create_event",
        {
            "title": "Jornada",
            "start": f"{soon}T08:30",
            "end": f"{soon}T18:00",
            "calendar": "Trabajo",
            "repeat": {"freq": "daily"},
        },
    )
    await call(
        api,
        "create_event",
        {
            "title": "Fiesta local de prueba",
            "start": str(soon),
            "all_day": True,
            "calendar": "Festivos locales",
        },
    )
    window = {"from": str(soon), "to": str(soon + timedelta(days=2)), "calendars": ["Trabajo"]}
    assert len((await call(api, "get_events", window, READ))["backgrounds"]) == 2

    freed = await call(api, "set_days_off", {"calendar": "Trabajo", "source": "Festivos locales"})

    assert freed["updated"]["days_off_from"] == ["Festivos locales"]
    days = (await call(api, "get_events", window, READ))["backgrounds"]
    assert [one["start"][:10] for one in days] == [str(soon + timedelta(days=1))]

    back = await call(
        api, "set_days_off", {"calendar": work["id"], "source": local["id"], "off": False}
    )
    assert "days_off_from" not in back["updated"]
    assert len((await call(api, "get_events", window, READ))["backgrounds"]) == 2


async def test_a_layer_is_not_made_twice_nor_with_the_read_role(api) -> None:
    await api.get("/calendars")

    again = await call(api, "create_calendar", {"name": "personal"})
    assert "ya hay una capa" in again["error"]

    response = await api.post("/tools/create_calendar", json={"name": "Otra"}, headers=READ)
    assert response.status_code == 403


async def test_claude_reads_the_catalogue_and_what_a_source_asks(api, hub_app, monkeypatch) -> None:
    from hub import catalogue

    async def regions(_client, _query, parent):
        return [{"code": f"{parent}-XX", "name": "Región de prueba"}]

    monkeypatch.setitem(catalogue.BY_ID["holidays"].searches, "regions", regions)

    menu = await call(api, "get_sources", {}, READ)

    sources = {one["provider"]: one for one in menu["sources"]}
    assert {"holidays", "formula1", "football", "ical"} <= set(sources)
    asks = {one["key"]: one for one in sources["holidays"]["asks"]}
    assert asks["region"]["depends_on"] == "country" and asks["region"]["optional"] is True
    assert sources["holidays"]["subscribed"] == []

    options = await call(
        api, "get_sources", {"provider": "holidays", "ask": "region", "parent": "ES"}, READ
    )
    assert options["options"] == [{"code": "ES-XX", "name": "Región de prueba"}]

    half = await call(api, "get_sources", {"provider": "holidays"}, READ)
    assert "provider" in half["error"] and "ask" in half["error"]


async def test_claude_subscribes_and_unsubscribes(api, hub_app) -> None:
    await api.get("/calendars")
    done = await call(
        api,
        "subscribe",
        {
            "provider": "holidays",
            "name": "Festivos de prueba",
            "params": {"country": "ES", "region": "ES-NC"},
        },
    )

    layer = done["subscribed"]
    assert (layer["name"], layer["origin"]) == ("Festivos de prueba", "subscription")
    calendars = (await call(api, "get_calendars", {}, READ))["calendars"]
    [mine] = [one for one in calendars if one["name"] == "Festivos de prueba"]
    plugged = [one for one in await hub_connections(hub_app) if one["provider"] == "holidays"]
    assert len(plugged) == 1

    twice = await call(
        api, "subscribe", {"provider": "formula1", "name": "festivos de prueba", "params": {}}
    )
    assert "ya hay una capa" in twice["error"]

    own = await call(api, "unsubscribe", {"calendar": "Personal"})
    assert "no es una suscripción" in own["error"]

    gone = await call(api, "unsubscribe", {"calendar": "Festivos de prueba"})

    assert gone == {"unsubscribed": "Festivos de prueba"}
    assert mine["id"] not in [one["id"] for one in (await api.get("/calendars")).json()]
    assert [one for one in await hub_connections(hub_app) if one["provider"] == "holidays"] == []


async def test_with_the_read_role_nothing_reaches_the_hub(api, hub_app) -> None:
    response = await api.post(
        "/tools/subscribe",
        json={"provider": "formula1", "name": "La F1", "params": {}},
        headers=READ,
    )

    assert response.status_code == 403
    assert [one for one in await hub_connections(hub_app) if one["provider"] == "formula1"] == []


async def test_what_the_hub_refuses_comes_back_with_its_reason(api, hub_app) -> None:
    refused = await call(
        api, "subscribe", {"provider": "ical", "name": "Nada", "params": {"url": "no"}}
    )

    assert "https://" in refused["error"]
    names = [one["name"] for one in (await call(api, "get_calendars", {}, READ))["calendars"]]
    assert "Nada" not in names
