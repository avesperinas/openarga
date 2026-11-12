from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from travel_kit import make_trip, place

import arga_agenda

BUDAPEST = {
    "name": "Budapest",
    "lat": 47.4979,
    "lon": 19.0402,
    "country_code": "HU",
    "osm_type": "relation",
    "osm_id": 21,
}


async def blocks_out(schema) -> list[dict]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        rows = await connection.execute(
            text("select payload from travel.travel_outbox where type = 'travel.block' order by id")
        )
        return [row.payload for row in rows]


async def dinner(api, status: str = "confirmed") -> tuple[str, str]:
    trip = await make_trip(api, "Budapest", "2027-11-11", "2027-11-14", status=status)
    city = await place(api, BUDAPEST)
    made = await api.post(
        f"/trips/{trip['id']}/stays",
        json={"place_id": city["id"], "arrives_on": "2027-11-11", "leaves_on": "2027-11-14"},
    )
    assert made.status_code == 201, made.text
    made = await api.post(
        f"/trips/{trip['id']}/blocks",
        json={
            "title": "Cena",
            "kind": "meal",
            "day": "2027-11-11",
            "starts_at": "19:30",
            "ends_at": "21:15",
            "confirmation": "MT-2",
        },
    )
    assert made.status_code == 201, made.text
    block = next(i["block"] for i in made.json()["days"][0]["items"] if i["block"])
    return trip["id"], block["id"]


async def test_a_dinner_at_half_past_seven_is_in_the_plan_layer_at_local_time(api, schema) -> None:
    await dinner(api)

    out = (await blocks_out(schema))[-1]
    agenda = arga_agenda.check_event(out)

    assert out["layer"] == "Plan"
    assert agenda["title"] == "Cena"
    assert agenda["tz"] == "Europe/Budapest"
    assert datetime.fromisoformat(agenda["start"]).hour == 19
    assert datetime.fromisoformat(agenda["end"]).minute == 15
    assert "MT-2" in agenda["location"]


async def test_without_a_time_it_leaves_the_calendar(api, schema) -> None:
    trip_id, block_id = await dinner(api)

    changed = await api.put(
        f"/trips/{trip_id}/blocks/{block_id}",
        json={"title": "Cena", "kind": "meal", "day": "2027-11-11"},
    )
    out = (await blocks_out(schema))[-1]

    assert changed.status_code == 200, changed.text
    assert out["removed"] is True
    assert out[arga_agenda.KEY]["status"] == "cancelled"


async def test_a_plan_publishes_nothing_and_back_to_plan_withdraws(api, schema) -> None:
    trip_id, _ = await dinner(api, status="plan")
    assert await blocks_out(schema) == []

    await api.put(f"/trips/{trip_id}/status", json={"status": "confirmed"})
    await api.put(f"/trips/{trip_id}/status", json={"status": "plan"})
    out = await blocks_out(schema)

    assert [one.get("removed", False) for one in out] == [False, True]
