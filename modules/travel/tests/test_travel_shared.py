from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from travel_kit import BRUGES, GHENT

from arga_tenancy import SPACES_HEADER, USER_HEADER, as_user
from travel import spaces, travel
from travel.main import app

SUBJECTS = {
    "ana": "5e0f2a11-3c4d-4e5f-8a6b-7c8d9e0f1a2b",
    "luis": "6f1a3b22-4d5e-4f60-9b7c-8d9e0f1a2b3c",
    "eva": "7a2b4c33-5e6f-4071-8c8d-9e0f1a2b3c4d",
}


@pytest.fixture
async def people(schema, database_url, monkeypatch):
    from kernel import db as kernel_db
    from kernel import migrate
    from kernel.main import app as kernel_app

    kernel_db.engine.cache_clear()
    await asyncio.to_thread(migrate.upgrade)
    monkeypatch.setattr(spaces, "transport", lambda: ASGITransport(app=kernel_app))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://k") as kernel:
        ids = {}
        for name, subject in SUBJECTS.items():
            ids[name] = (await kernel.post("/internal/users", json={"subject": subject})).json()[
                "id"
            ]
        casa = (
            await kernel.post(
                "/internal/spaces", json={"name": "Casa"}, headers={USER_HEADER: ids["ana"]}
            )
        ).json()["id"]
        code = (
            await kernel.post(f"/internal/spaces/{casa}/invites", headers={USER_HEADER: ids["ana"]})
        ).json()["code"]
        await kernel.post(
            "/internal/spaces/join", json={"code": code}, headers={USER_HEADER: ids["luis"]}
        )
    yield {**ids, "casa": casa}
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.spaces where id = :id"), {"id": casa})
        await connection.execute(
            text("delete from kernel.users where subject = any(:s)"),
            {"s": list(SUBJECTS.values())},
        )
    await kernel_db.engine().dispose()
    kernel_db.engine.cache_clear()


def _headers(people: dict, name: str) -> dict[str, str]:
    spaces_of = {"ana": [people["casa"]], "luis": [people["casa"]], "eva": []}[name]
    return {USER_HEADER: people[name], SPACES_HEADER: ",".join(spaces_of)}


@pytest.fixture
async def as_person(people):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://travel") as client:

        class Caller:
            async def __call__(self, name: str, method: str, path: str, headers=None, **kw):
                sent = {**_headers(people, name), **(headers or {})}
                return await client.request(method, path, headers=sent, **kw)

        yield Caller()


async def a_trip_in_flanders(call) -> str:
    created = await call(
        "ana",
        "POST",
        "/trips",
        json={"title": "Flandes", "starts_on": "2025-04-10", "ends_on": "2025-04-15"},
    )
    trip = created.json()["id"]
    brujas = (await call("ana", "POST", "/places", json=BRUGES)).json()["id"]
    await call(
        "ana",
        "POST",
        f"/trips/{trip}/stays",
        json={"place_id": brujas, "arrives_on": "2025-04-10", "leaves_on": "2025-04-12"},
    )
    await call(
        "ana",
        "POST",
        f"/trips/{trip}/expenses",
        json={"category": "lodging", "concept": "Hotel", "amount_eur": 120},
    )
    return trip


async def test_a_shared_trip_is_seen_and_edited_by_the_space_and_by_nobody_else(
    as_person, people
) -> None:
    trip = await a_trip_in_flanders(as_person)
    before = await as_person("luis", "GET", f"/trips/{trip}")

    shared = await as_person(
        "ana", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]}
    )
    luis = (await as_person("luis", "GET", f"/trips/{trip}")).json()
    gante = (await as_person("luis", "POST", "/places", json=GHENT)).json()["id"]
    added = await as_person(
        "luis",
        "POST",
        f"/trips/{trip}/visits",
        json={"place_id": gante, "visited_on": "2025-04-11"},
    )
    await as_person(
        "luis",
        "POST",
        f"/trips/{trip}/expenses",
        json={"category": "other", "concept": "Excursiones", "amount_eur": 30},
    )
    ana = (await as_person("ana", "GET", f"/trips/{trip}")).json()
    eva = await as_person("eva", "GET", f"/trips/{trip}")

    assert before.status_code == 404
    assert shared.status_code == 200, shared.text
    assert (shared.json()["space_id"], shared.json()["mine"]) == (people["casa"], True)
    assert (luis["mine"], [s["place"]["name"] for s in luis["stays"]]) == (False, ["Brujas"])
    assert added.status_code == 201, added.text
    assert [v["place"]["name"] for v in ana["visits"]] == ["Gante"]
    assert sorted((e["concept"], e["mine"]) for e in ana["expenses"]) == [
        ("Excursiones", False),
        ("Hotel", True),
    ]
    assert eva.status_code == 404


async def test_only_whoever_created_it_shares_unshares_or_deletes_it(as_person, people) -> None:
    trip = await a_trip_in_flanders(as_person)
    await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]})

    unshare = await as_person("luis", "PUT", f"/trips/{trip}/space", json={"space_id": None})
    delete = await as_person("luis", "DELETE", f"/trips/{trip}")
    outsider = await as_person("eva", "PUT", f"/trips/{trip}/space", json={"space_id": None})
    foreign = await as_person(
        "eva", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]}
    )

    assert (unshare.status_code, delete.status_code) == (409, 409)
    assert "solo" in unshare.json()["detail"]
    assert outsider.status_code == 404
    assert foreign.status_code == 404
    assert (await as_person("luis", "GET", f"/trips/{trip}")).status_code == 200


async def test_unsharing_keeps_what_others_added_with_their_places_copied(
    as_person, people
) -> None:
    trip = await a_trip_in_flanders(as_person)
    await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]})
    gante = (await as_person("luis", "POST", "/places", json=GHENT)).json()["id"]
    await as_person(
        "luis", "POST", f"/trips/{trip}/visits", json={"place_id": gante, "visited_on": None}
    )

    back = await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": None})
    luis = await as_person("luis", "GET", f"/trips/{trip}")
    with as_user(UUID(people["ana"])):
        async with app_connection() as connection:
            alone = await travel.trip(connection, trip)

    assert back.status_code == 200, back.text
    visit = back.json()["visits"][0]
    assert (back.json()["space_id"], visit["place"]["name"]) == (None, "Gante")
    assert visit["place"]["id"] != gante
    assert luis.status_code == 404
    assert [v.place.name for v in alone.visits] == ["Gante"]
    assert [s.place.name for s in alone.stays] == ["Brujas"]


async def test_a_trip_shared_with_you_enters_your_calendar_and_leaves_it(as_person, people) -> None:
    trip = await a_trip_in_flanders(as_person)
    await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]})

    luis = (UUID(people["luis"]), (UUID(people["casa"]),))
    with as_user(*luis):
        async with app_connection() as connection:
            await travel.sync_shared(connection)
            shared = await calendar(connection, trip)
    await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": None})
    with as_user(*luis):
        async with app_connection() as connection:
            await travel.sync_shared(connection)
            gone = await calendar(connection, trip)

    assert shared == ["confirmed"]
    assert gone == ["confirmed", "cancelled"]


async def test_the_saved_places_offered_are_only_yours(as_person, people) -> None:
    trip = await a_trip_in_flanders(as_person)
    await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]})

    offered = (await as_person("luis", "GET", "/places")).json()
    luis_brujas = (await as_person("luis", "POST", "/places", json=BRUGES)).json()
    ana_brujas = (await as_person("ana", "GET", f"/trips/{trip}")).json()["stays"][0]["place"]

    assert offered == []
    assert luis_brujas["id"] != ana_brujas["id"]


async def test_claude_shares_a_trip_by_the_spaces_name_and_says_when_there_is_none(
    as_person, people
) -> None:
    trip = await a_trip_in_flanders(as_person)

    async def tool(name: str, arguments: dict) -> dict:
        response = await as_person(
            name,
            "POST",
            "/tools/share_trip",
            json=arguments,
            headers={"x-arga-scopes": "travel:write"},
        )
        assert response.status_code == 200, response.text
        return response.json()["content"]

    unknown = await tool("ana", {"trip_id": trip, "space": "Oficina"})
    shared = await tool("ana", {"trip_id": trip, "space": "casa"})
    by_luis = await tool("luis", {"trip_id": trip, "space": None})
    seen = await as_person("luis", "GET", f"/trips/{trip}")

    assert (unknown["code"], unknown["conflicts"]) == ("NOT_FOUND", [{"space": "Casa"}])
    assert (shared["trip"]["shared"], shared["trip"]["mine"]) == (True, True)
    assert by_luis["code"] == "NOT_OWNER"
    assert seen.status_code == 200


def app_connection():
    from contextlib import asynccontextmanager

    from travel.db import engine

    @asynccontextmanager
    async def opened():
        async with engine().begin() as connection:
            await connection.execute(text('set local role "mod_travel"'))
            yield connection

    return opened()


async def calendar(connection, trip_id: str) -> list[str]:
    rows = await connection.execute(
        text("""
            select payload->'agenda'->>'status' as status from travel.travel_outbox
            where type = 'travel.trip' and payload->>'trip_id' = :id order by id
        """),
        {"id": trip_id},
    )
    return [row.status for row in rows]


async def test_the_itinerary_is_shared_and_stays_whole_when_unshared(as_person, people) -> None:
    trip = await a_trip_in_flanders(as_person)
    await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]})
    gante = (await as_person("luis", "POST", "/places", json=GHENT)).json()["id"]
    added = await as_person(
        "luis",
        "POST",
        f"/trips/{trip}/blocks",
        json={"title": "Catedral de Gante", "day": "2025-04-11", "place_id": gante},
    )
    seen = (await as_person("ana", "GET", f"/trips/{trip}/days")).json()

    back = await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": None})
    kept = (await as_person("ana", "GET", f"/trips/{trip}/days")).json()

    assert added.status_code == 201, added.text
    titles = [i["block"]["title"] for i in seen["days"][1]["items"] if i["type"] == "block"]
    assert titles == ["Catedral de Gante"]
    assert back.status_code == 200, back.text
    block = next(i["block"] for i in kept["days"][1]["items"] if i["type"] == "block")
    assert block["place"]["name"] == "Gante" and block["place"]["id"] != gante
    assert block["mine"] is True


async def test_an_idea_is_shared_and_stays_whole_when_unshared(as_person, people) -> None:
    created = await as_person("ana", "POST", "/ideas", json={"title": "Flandes"})
    idea = created.json()["id"]
    shared = await as_person(
        "ana", "PUT", f"/ideas/{idea}/space", json={"space_id": people["casa"]}
    )
    gante = (await as_person("luis", "POST", "/places", json=GHENT)).json()["id"]
    added = await as_person("luis", "POST", f"/ideas/{idea}/places", json={"place_id": gante})
    eva = await as_person("eva", "GET", f"/ideas/{idea}")

    back = await as_person("ana", "PUT", f"/ideas/{idea}/space", json={"space_id": None})
    luis = await as_person("luis", "GET", f"/ideas/{idea}")

    assert shared.status_code == 200, shared.text
    assert added.status_code == 201, added.text
    assert eva.status_code == 404
    assert back.status_code == 200, back.text
    [destination] = back.json()["places"]
    assert destination["place"]["name"] == "Gante" and destination["place"]["id"] != gante
    assert luis.status_code == 404


async def test_each_traveller_is_someone_of_the_space_and_both_see_the_same_balance(
    as_person, people
) -> None:
    created = await as_person(
        "ana",
        "POST",
        "/trips",
        json={
            "title": "Lisboa",
            "starts_on": "2027-03-10",
            "ends_on": "2027-03-12",
            "travellers": 2,
            "companions": ["Luis"],
        },
    )
    trip = created.json()["id"]
    travellers = (await as_person("ana", "GET", f"/trips/{trip}/travellers")).json()
    luis_traveller = next(one["id"] for one in travellers if one["name"] == "Luis")
    too_soon = await as_person(
        "ana",
        "PATCH",
        f"/trips/{trip}/travellers/{luis_traveller}",
        json={"member_user_id": people["luis"]},
    )
    await as_person("ana", "PUT", f"/trips/{trip}/space", json={"space_id": people["casa"]})
    outsider = await as_person(
        "ana",
        "PATCH",
        f"/trips/{trip}/travellers/{luis_traveller}",
        json={"member_user_id": people["eva"]},
    )
    linked = await as_person(
        "ana",
        "PATCH",
        f"/trips/{trip}/travellers/{luis_traveller}",
        json={"member_user_id": people["luis"]},
    )
    await as_person(
        "luis",
        "POST",
        f"/trips/{trip}/expenses",
        json={
            "category": "other",
            "concept": "Cena",
            "amount": "80",
            "currency": "EUR",
            "paid_by": luis_traveller,
        },
    )
    seen_by = {
        name: (await as_person(name, "GET", f"/trips/{trip}/balance")).json()
        for name in ("ana", "luis")
    }

    assert too_soon.status_code == 409
    assert outsider.status_code == 409
    assert linked.status_code == 200, linked.text
    luis_view = (await as_person("luis", "GET", f"/trips/{trip}/travellers")).json()
    assert {one["name"]: one["me"] for one in luis_view} == {"Yo": False, "Luis": True}
    nets = {
        name: {one["traveller"]["id"]: one["net_eur"] for one in balance["people"]}
        for name, balance in seen_by.items()
    }
    assert nets["ana"] == nets["luis"]
    assert nets["luis"][luis_traveller] == 40.0
