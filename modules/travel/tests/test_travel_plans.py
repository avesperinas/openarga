from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import text
from travel_kit import BRUGES, GHENT, LILLE, make_trip, place, stay

from travel import metrics, travel, widgets
from travel.db import engine

SOON = travel.today() + timedelta(days=40)


def ahead(days: int) -> str:
    return (SOON + timedelta(days=days)).isoformat()


async def agenda(schema) -> list[dict]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        rows = await connection.execute(
            text("select payload from travel.travel_outbox where type = 'travel.trip' order by id")
        )
        return [row.payload["agenda"] for row in rows]


async def test_a_plan_stays_out_of_the_calendar_until_it_is_confirmed(api, schema) -> None:
    plan = await make_trip(api, "Japón", ahead(0), ahead(14), status="plan")
    assert plan["status"] == "plan" and plan["phase"] == "plan"
    await stay(api, plan["id"], BRUGES, ahead(0), ahead(3))
    assert await agenda(schema) == []

    confirmed = await api.put(f"/trips/{plan['id']}/status", json={"status": "confirmed"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["phase"] == "upcoming"
    published = await agenda(schema)
    assert [one["status"] for one in published] == ["confirmed"]
    assert published[0]["uid"] == f"travel:trip:{plan['id']}"

    await api.put(f"/trips/{plan['id']}/status", json={"status": "plan"})
    assert [one["status"] for one in await agenda(schema)] == ["confirmed", "cancelled"]

    await api.put(f"/trips/{plan['id']}/status", json={"status": "confirmed"})
    assert [one["status"] for one in await agenda(schema)] == [
        "confirmed",
        "cancelled",
        "confirmed",
    ]


async def test_a_plan_that_was_never_confirmed_leaves_no_trace_when_deleted(api, schema) -> None:
    plan = await make_trip(api, "Islandia", ahead(0), ahead(7), status="plan")
    assert (await api.delete(f"/trips/{plan['id']}")).status_code == 204
    assert await agenda(schema) == []


async def test_after_a_rollback_the_plans_published_by_the_old_code_are_withdrawn(
    api, schema
) -> None:
    plan = await make_trip(api, "Japón", ahead(0), ahead(14), status="plan")
    kept = await make_trip(api, "Flandes", "2025-04-10", "2025-04-15")
    old = travel._agenda(plan["id"], "Japón", SOON, SOON + timedelta(days=14))
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        await connection.execute(
            text(
                "insert into travel.travel_outbox (type, payload, dedup_hash) "
                "values ('travel.trip', cast(:payload as jsonb), 'old-code')"
            ),
            {"payload": json.dumps({"trip_id": plan["id"], "title": "Japón", "agenda": old})},
        )

    for _ in range(2):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_travel"'))
            await travel.backfill(connection)

    published = await agenda(schema)
    of_plan = [one["status"] for one in published if one["uid"].endswith(plan["id"])]
    of_kept = [one["status"] for one in published if one["uid"].endswith(kept["id"])]
    assert of_plan == ["confirmed", "cancelled"]
    assert of_kept == ["confirmed"]


async def test_what_has_not_happened_does_not_count(api) -> None:
    done = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    await stay(api, done["id"], BRUGES, "2025-04-10", "2025-04-12")
    upcoming = await make_trip(api, "Lille", ahead(0), ahead(2))
    await stay(api, upcoming["id"], LILLE, ahead(0), ahead(2))
    plan = await make_trip(api, "Gante", ahead(10), ahead(12), status="plan")
    await stay(api, plan["id"], GHENT, ahead(10), ahead(12))

    phases = {one["title"]: one["phase"] for one in (await api.get("/atlas")).json()["trips"]}
    assert phases == {"Flandes": "done", "Lille": "upcoming", "Gante": "plan"}

    figures = (await api.get("/stats")).json()
    assert (figures["trips"], figures["countries"]) == (1, 1)

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_travel_read"'))
        found = await metrics.build(connection)
        nxt = await widgets.next_trip(connection)
    trips = [one for one in found if one["key"] == "travel.trips"]
    assert sum(one["value"] for one in trips) == 1
    assert nxt["body"]["events"][0]["title"] == "Lille"


async def test_moving_a_plan_moves_everything_with_a_date(api) -> None:
    plan = await make_trip(api, "Japón", ahead(0), ahead(6), status="plan")
    bruges = await place(api, BRUGES)
    ghent = await place(api, GHENT)
    await api.post(
        f"/trips/{plan['id']}/stays",
        json={"place_id": bruges["id"], "arrives_on": ahead(0), "leaves_on": ahead(3)},
    )
    await api.post(
        f"/trips/{plan['id']}/visits", json={"place_id": ghent["id"], "visited_on": ahead(2)}
    )

    body = {"title": "Japón", "starts_on": ahead(30), "ends_on": ahead(36)}
    refused = await api.put(f"/trips/{plan['id']}", json=body)
    assert refused.status_code == 409

    moved = await api.put(f"/trips/{plan['id']}?shift=true", json=body)
    assert moved.status_code == 200, moved.text
    found = moved.json()
    assert (found["stays"][0]["arrives_on"], found["stays"][0]["leaves_on"]) == (
        ahead(30),
        ahead(33),
    )
    assert found["visits"][0]["visited_on"] == ahead(32)
    assert found["status"] == "plan"
