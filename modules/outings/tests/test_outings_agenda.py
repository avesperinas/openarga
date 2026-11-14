from __future__ import annotations

import secrets
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from outings_world import TODAY, Hub, derive, leisure
from sqlalchemy import text

from outings import agenda
from outings.db import engine

MODULES = Path(__file__).resolve().parents[2]
TOKEN = secrets.token_hex(16)


async def test_what_the_hub_brings_is_in_the_agenda_of_its_period(api, kernel) -> None:
    feed = Hub(kernel)
    await feed.bring(
        leisure("Hoy mismo", TODAY, time="20:00"),
        leisure("In ten days", TODAY + timedelta(days=10), category="eat"),
        leisure("Next year", TODAY + timedelta(days=200)),
    )

    assert (await derive())["added"] == 3
    week = (await api.get("/agenda", params={"period": "week"})).json()
    year = (await api.get("/agenda", params={"period": "year"})).json()
    eat = (await api.get("/agenda", params={"period": "year", "category": "eat"})).json()

    assert [event["title"] for event in week["events"]] == ["Hoy mismo"]
    assert len(year["events"]) == 3
    assert [event["title"] for event in eat["events"]] == ["In ten days"]
    today = week["events"][0]
    assert today["time"] == "20:00"
    assert today["links"] == [
        {
            "name": "Synthetic agenda",
            "url": "https://agenda.example/Hoy mismo",
            "page": "https://agenda.example/agenda",
        }
    ]
    assert (await derive()) == {"added": 0, "changed": 0, "refreshed": 0}


def test_this_weekend_is_friday_to_sunday() -> None:
    wednesday = date(2026, 9, 30)
    saturday = date(2026, 10, 3)

    assert agenda.window("weekend", wednesday) == (date(2026, 10, 2), date(2026, 10, 4))
    assert agenda.window("weekend", saturday) == (saturday, date(2026, 10, 4))
    assert agenda.window("week", wednesday) == (wednesday, date(2026, 10, 6))


async def test_a_new_version_changes_the_event_and_a_removed_agenda_hides_it(api, kernel) -> None:
    feed = Hub(kernel)
    first = leisure("Concierto", TODAY + timedelta(days=2))
    await feed.bring(first)
    await derive()
    [shown] = (await api.get("/agenda", params={"period": "month"})).json()["events"]

    await feed.bring({**leisure("Concierto", TODAY + timedelta(days=2), time="21:00")})
    assert (await derive())["changed"] == 1
    again = (await api.get(f"/events/{shown['id']}")).json()
    assert again["time"] == "21:00" and again["id"] == shown["id"]

    await feed.removed()
    await derive()
    assert (await api.get("/agenda", params={"period": "month"})).json()["events"] == []


async def test_i_fancy_it_is_a_dated_plan_in_wishes_once(api, kernel) -> None:
    feed = Hub(kernel)
    await feed.bring(
        leisure(
            "Synthetic food days",
            TODAY + timedelta(days=3),
            TODAY + timedelta(days=5),
            category="eat",
        )
    )
    await derive()
    [event] = (await api.get("/agenda", params={"period": "month"})).json()["events"]

    saved = (await api.post(f"/events/{event['id']}/save")).json()
    twice = (await api.post(f"/events/{event['id']}/save")).json()

    assert saved["id"] == twice["id"]
    assert (saved["kind"], saved["name"], saved["event_id"]) == (
        "plan",
        "Synthetic food days",
        event["id"],
    )
    assert saved["starts_on"] == (TODAY + timedelta(days=3)).isoformat()
    assert saved["place"]["name"] == "Synthetic hall" and saved["place"]["town"] == "Pamplona"
    assert (await api.get(f"/events/{event['id']}")).json()["wish_id"] == saved["id"]


@pytest.fixture
async def planner(kernel, schema):

    from arga_testing import fresh_modules

    async with schema.begin() as connection:
        await fresh_modules(connection, "planner", "outings", fresh=["planner"])
    yield
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'planner'"))


async def test_to_planner_publishes_it_with_the_agenda_contract_and_planner_sees_it(
    api, kernel, planner, schema, person
) -> None:
    from arga_tenancy import as_user
    from outings import publisher

    feed = Hub(kernel)
    await feed.bring(leisure("Orquesta", TODAY + timedelta(days=1), time="19:30"))
    await derive()
    [event] = (await api.get("/agenda", params={"period": "week"})).json()["events"]

    put = (await api.put(f"/events/{event['id']}/calendar", params={"on": "true"})).json()
    assert put["in_calendar"] is True
    with as_user(person):
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_outings"'))
            published = await publisher.publish_pending(connection, kernel)
    assert published["published"] == 1

    async with schema.connect() as connection:
        await connection.execute(text("set role mod_planner"))
        await connection.execute(
            text("select set_config('arga.user_id', :id, false)"), {"id": str(person)}
        )
        [row] = (
            await connection.execute(
                text("select payload from planner.events where type = 'outings.plan'")
            )
        ).all()
        await connection.execute(text("reset role"))
    dated = row.payload["agenda"]
    assert dated["uid"] == f"outings:event:{event['id']}"
    assert dated["all_day"] is False and dated["tz"] == "Europe/Madrid"
    assert dated["start"].startswith(f"{(TODAY + timedelta(days=1)).isoformat()}T19:30")
    assert dated["href"] == f"/outings/events/{event['id']}"


async def test_plugging_from_settings_creates_the_agenda_in_hub(api, hub_app) -> None:
    listed = (await api.get("/agenda/sources")).json()
    assert listed["failed"] is None and listed["plugged"] == []
    [offered] = listed["offered"]
    [pages] = offered["asks"]
    assert pages["kind"] == "checks" and len(pages["defaults"]) == 4

    plugged = await api.post(
        "/agenda/sources",
        json={
            "provider": offered["provider"],
            "label": offered["name"],
            "params": {"pages": pages["defaults"]},
        },
    )
    added = await api.post(
        "/agenda/sources",
        json={
            "provider": offered["provider"],
            "label": "Teatro",
            "params": {"url": "https://teatro.example/agenda"},
        },
    )
    bad = await api.post(
        "/agenda/sources",
        json={"provider": offered["provider"], "label": "Mal", "params": {"url": "nada"}},
    )

    assert plugged.status_code == 201, plugged.text
    assert added.status_code == 201, added.text
    assert bad.status_code == 422 and "https" in bad.json()["detail"]
    async with AsyncClient(transport=ASGITransport(app=hub_app), base_url="http://hub") as c:
        teatro = (await c.get(f"/connections/{added.json()['connection']}")).json()
    assert teatro["label"] == "Teatro"
    removed = await api.delete(f"/agenda/sources/{plugged.json()['connection']}")
    assert removed.json() == {"removed": True}


OTHER = str(uuid4())


async def test_the_same_concert_in_two_agendas_is_one_event_with_two_links(api, kernel) -> None:
    feed = Hub(kernel)
    day = TODAY + timedelta(days=4)
    await feed.bring(leisure("Euskadiko Orkestra", day, time="19:30"))
    await feed.bring(
        {
            **leisure("EUSKADIKO ORKESTRA · Season 26/27", day, venue="Baluarte"),
            "connection": OTHER,
            "key": "otra",
            "link": "https://ayuntamiento.example/orquesta",
            "source_name": "Synthetic town hall",
        }
    )
    await feed.bring(leisure("Otro concierto distinto", day))

    result = await derive()
    shown = (await api.get("/agenda", params={"period": "month"})).json()["events"]

    assert result["merged"] == 1
    assert len(shown) == 2
    [joined] = [event for event in shown if len(event["links"]) == 2]
    assert {link["name"] for link in joined["links"]} == {
        "Synthetic agenda",
        "Synthetic town hall",
    }

    found = (await api.get(f"/events/{joined['id']}")).json()
    assert len(found["sources"]) == 2
    other = next(one for one in found["sources"] if one["name"] == "Synthetic town hall")
    apart = await api.post(f"/events/{joined['id']}/split/{other['id']}")
    assert apart.status_code == 200, apart.text
    assert len((await api.get("/agenda", params={"period": "month"})).json()["events"]) == 3

    await feed.bring(
        {
            **leisure("EUSKADIKO ORKESTRA · Season 26/27", day, venue="Baluarte · sala"),
            "connection": OTHER,
            "key": "otra",
            "link": "https://ayuntamiento.example/orquesta",
            "source_name": "Synthetic town hall",
        }
    )
    await derive()
    assert len((await api.get("/agenda", params={"period": "month"})).json()["events"]) == 3
    alone = await api.post(f"/events/{apart.json()['id']}/split/{other['id']}")
    assert alone.status_code == 409


def test_titles_match_once_normalised_and_different_ones_do_not() -> None:
    assert agenda.same_title("Euskadiko Orkestra", "EUSKADIKO ORKESTRA - Temporada 26/27")
    assert agenda.same_title("Semana de la Croqueta", "Semana de la croqueta")
    assert not agenda.same_title("Christmas Concert", "New Year Concert")
    assert agenda.same_town(None, "Pamplona") and not agenda.same_town("Tudela", "Pamplona")


async def test_what_comes_back_every_year_is_gone_everywhere(api, kernel) -> None:
    await Hub(kernel).bring(
        leisure(
            "XX Synthetic Croquette Week",
            TODAY + timedelta(days=3),
            category="eat",
            recurring=True,
        )
    )
    await derive()
    shown = (await api.get("/agenda", params={"period": "month"})).json()
    [event] = shown["events"]
    full = (await api.get(f"/events/{event['id']}")).json()
    brief = (await api.get("/agenda/prompt")).json()["prompt"]

    assert "returning" not in shown
    assert "returns" not in full and "recurring" not in full
    assert (await api.get("/returning")).status_code == 404
    assert (await api.put(f"/events/{event['id']}/notify")).status_code in (404, 405)
    assert "Avisarme" not in brief and "recurring" not in brief
