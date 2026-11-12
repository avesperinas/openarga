from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from travel_kit import MADRID, SEVILLE, make_trip, place

import arga_agenda
from travel import zones

LISBON = {
    "name": "Lisboa",
    "lat": 38.7223,
    "lon": -9.1393,
    "country_code": "PT",
    "osm_type": "relation",
    "osm_id": 11,
}
TOKYO = {
    "name": "Tokio",
    "lat": 35.6762,
    "lon": 139.6503,
    "country_code": "JP",
    "osm_type": "relation",
    "osm_id": 12,
}
LAS_PALMAS = {
    "name": "Las Palmas",
    "lat": 28.1235,
    "lon": -15.4363,
    "country_code": "ES",
    "osm_type": "relation",
    "osm_id": 13,
}


async def legs_out(schema) -> list[dict]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        rows = await connection.execute(
            text("select payload from travel.travel_outbox where type = 'travel.leg' order by id")
        )
        return [row.payload for row in rows]


async def a_leg(api, trip_id: str, origin: dict, target: dict, **fields) -> dict:
    a = await place(api, {**origin, "country_code": origin.get("country_code", "ES")})
    b = await place(api, {**target, "country_code": target.get("country_code", "ES")})
    saved = await api.post(
        f"/trips/{trip_id}/legs",
        json={"from_place_id": a["id"], "to_place_id": b["id"], **fields},
    )
    assert saved.status_code == 201, saved.text
    return saved.json()["legs"][-1]


async def test_a_flight_goes_from_its_local_departure_to_its_local_arrival(api, schema) -> None:
    trip = await make_trip(api, "Lisboa", "2025-04-10", "2025-04-13")
    leg = await a_leg(
        api,
        trip["id"],
        MADRID,
        LISBON,
        mode="plane",
        travelled_on="2025-04-10",
        departs_at="07:15",
        arrives_at="07:40",
        carrier="Iberia",
        number="IB3102",
        from_code="MAD",
        terminal="4",
    )

    out = (await legs_out(schema))[-1]
    assert out["layer"] == "Trayectos"
    item = arga_agenda.check_event(out)
    assert item["uid"] == f"travel:leg:{leg['id']}"
    assert item["title"] == "Vuelo Iberia IB3102 · Madrid → Lisboa"
    assert item["location"] == "Madrid (MAD) · terminal 4"
    assert item["all_day"] is False and item["tz"] == "Europe/Madrid"
    start, end = datetime.fromisoformat(item["start"]), datetime.fromisoformat(item["end"])
    assert start.isoformat() == "2025-04-10T07:15:00+02:00"
    assert end.isoformat() == "2025-04-10T07:40:00+01:00"
    assert (end - start).total_seconds() == 85 * 60
    assert item["href"] == f"/travel/viajes/{trip['id']}/dias/2025-04-10"


async def test_an_arrival_earlier_than_the_departure_without_a_day_is_the_next_day(
    api, schema
) -> None:
    trip = await make_trip(api, "Japón", "2025-04-10", "2025-04-20")
    await a_leg(
        api,
        trip["id"],
        MADRID,
        TOKYO,
        mode="plane",
        travelled_on="2025-04-10",
        departs_at="21:00",
        arrives_at="17:30",
    )

    item = arga_agenda.check_event((await legs_out(schema))[-1])
    assert item["end"] == "2025-04-11T17:30:00+09:00"


async def test_a_leg_without_a_time_is_a_whole_day_and_one_without_a_date_is_not_out(
    api, schema
) -> None:
    trip = await make_trip(api, "Andalucía", "2025-04-10", "2025-04-13")
    await a_leg(api, trip["id"], MADRID, SEVILLE, mode="train", travelled_on="2025-04-10")
    await a_leg(api, trip["id"], SEVILLE, MADRID, mode="car")

    out = await legs_out(schema)
    assert len(out) == 1
    item = arga_agenda.check_event(out[0])
    assert item["title"] == "Tren · Madrid → Sevilla"
    assert (item["all_day"], item["start"], item["end"]) == (True, "2025-04-10", "2025-04-11")


async def test_a_leg_leaves_the_calendar_when_removed_or_left_without_a_date(api, schema) -> None:
    trip = await make_trip(api, "Andalucía", "2025-04-10", "2025-04-13")
    going = await a_leg(api, trip["id"], MADRID, SEVILLE, mode="train", travelled_on="2025-04-10")
    back = await a_leg(api, trip["id"], SEVILLE, MADRID, mode="train", travelled_on="2025-04-13")

    removed = await api.delete(f"/trips/{trip['id']}/legs/{going['id']}")
    assert removed.status_code in (200, 204), removed.text
    undated = await api.put(
        f"/trips/{trip['id']}/legs/{back['id']}",
        json={
            "from_place_id": back["from_place"]["id"],
            "to_place_id": back["to_place"]["id"],
            "mode": "train",
            "travelled_on": None,
        },
    )
    assert undated.status_code == 200, undated.text

    last = {}
    for payload in await legs_out(schema):
        last[payload["leg_id"]] = payload
    assert {leg_id: one["agenda"]["status"] for leg_id, one in last.items()} == {
        going["id"]: "cancelled",
        back["id"]: "cancelled",
    }
    assert all(one["agenda"]["uid"] == f"travel:leg:{leg_id}" for leg_id, one in last.items())


async def test_a_plan_keeps_its_legs_out_and_a_deleted_trip_takes_them_away(api, schema) -> None:
    plan = await make_trip(api, "Lisboa", "2025-04-10", "2025-04-13", status="plan")
    await a_leg(
        api, plan["id"], MADRID, LISBON, mode="plane", travelled_on="2025-04-10", departs_at="07:15"
    )
    assert await legs_out(schema) == []

    await api.put(f"/trips/{plan['id']}/status", json={"status": "confirmed"})
    assert [one["agenda"]["status"] for one in await legs_out(schema)] == ["confirmed"]

    await api.put(f"/trips/{plan['id']}/status", json={"status": "plan"})
    await api.put(f"/trips/{plan['id']}/status", json={"status": "confirmed"})
    assert (await api.delete(f"/trips/{plan['id']}")).status_code == 204
    assert [one["agenda"]["status"] for one in await legs_out(schema)] == [
        "confirmed",
        "cancelled",
        "confirmed",
        "cancelled",
    ]


async def test_editing_something_else_of_the_trip_publishes_nothing_new(api, schema) -> None:
    trip = await make_trip(api, "Andalucía", "2025-04-10", "2025-04-13")
    await a_leg(api, trip["id"], MADRID, SEVILLE, mode="train", travelled_on="2025-04-10")
    await api.put(
        f"/trips/{trip['id']}",
        json={"title": "Sur", "starts_on": "2025-04-10", "ends_on": "2025-04-13"},
    )
    assert len(await legs_out(schema)) == 1


def test_the_zone_of_a_place_is_that_of_its_country_nearest_city() -> None:
    assert zones.zone_of("ES", 40.4168, -3.7038) == "Europe/Madrid"
    assert zones.zone_of("ES", LAS_PALMAS["lat"], LAS_PALMAS["lon"]) == "Atlantic/Canary"
    assert zones.zone_of("JP", None, None) == "Asia/Tokyo"
    assert zones.zone_of("US", 40.7128, -74.0060) == "America/New_York"
    assert zones.zone_of("US", 34.0522, -118.2437) == "America/Los_Angeles"
    assert zones.zone_of(None, None, None) == "Europe/Madrid"
