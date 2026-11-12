from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from travel_kit import BRUGES, GHENT, make_trip, place, stay

from travel import itinerary
from travel.db import engine


async def days(api, trip_id: str) -> dict:
    response = await api.get(f"/trips/{trip_id}/days")
    assert response.status_code == 200, response.text
    return response.json()


def titles(found: dict, number: int) -> list[str]:
    return [
        item["block"]["title"]
        for item in found["days"][number - 1]["items"]
        if item["type"] == "block"
    ]


async def block(api, trip_id: str, **body) -> dict:
    response = await api.post(f"/trips/{trip_id}/blocks", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_day_is_what_you_leave_how_you_travel_where_you_arrive_and_what_you_do(api):
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-11")
    await stay(api, trip["id"], GHENT, "2025-04-11", "2025-04-12")
    await block(api, trip["id"], title="Paseo", day="2025-04-10")
    await block(api, trip["id"], title="Cena", kind="meal", day="2025-04-10", starts_at="20:30")
    await block(api, trip["id"], title="Shopping", day="2025-04-10", starts_at="10:00")

    found = await days(api, trip["id"])

    assert [d["number"] for d in found["days"]] == [1, 2, 3]
    assert titles(found, 1) == ["Shopping", "Cena", "Paseo"]
    second = [item["type"] for item in found["days"][1]["items"]]
    assert second == ["check_out", "check_in"]
    assert found["days"][0]["sleeping"]["place"]["name"] == "Brujas"
    assert found["days"][2]["sleeping"] is None


async def test_dragging_a_block_to_another_day_takes_the_visit_with_it(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    ghent = await place(api, GHENT)
    await block(api, trip["id"], title="Desayuno", kind="meal", day="2025-04-11")
    found = await block(api, trip["id"], title="Catedral", day="2025-04-10", place_id=ghent["id"])
    moved_id = titles(found, 1) and found["days"][0]["items"][0]["block"]["id"]

    moved = await api.put(
        f"/trips/{trip['id']}/blocks/{moved_id}/position",
        json={"day": "2025-04-11", "position": 0},
    )
    visits = (await api.get(f"/trips/{trip['id']}")).json()["visits"]

    assert moved.status_code == 200, moved.text
    assert titles(moved.json(), 1) == []
    assert titles(moved.json(), 2) == ["Catedral", "Desayuno"]
    assert [(v["place"]["name"], v["visited_on"]) for v in visits] == [("Gante", "2025-04-11")]


async def test_only_an_activity_with_a_place_counts_as_visited(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    ghent = await place(api, GHENT)
    found = await block(api, trip["id"], title="Gante", day="2025-04-10", place_id=ghent["id"])
    block_id = found["days"][0]["items"][0]["block"]["id"]
    assert (await api.get(f"/trips/{trip['id']}")).json()["countries"] == ["BE"]

    meal = await api.put(
        f"/trips/{trip['id']}/blocks/{block_id}",
        json={
            "title": "Comida en Gante",
            "kind": "meal",
            "day": "2025-04-10",
            "place_id": ghent["id"],
        },
    )
    assert meal.status_code == 200, meal.text
    assert (await api.get(f"/trips/{trip['id']}")).json()["visits"] == []

    await api.put(
        f"/trips/{trip['id']}/blocks/{block_id}",
        json={"title": "Gante", "day": "2025-04-10", "place_id": ghent["id"]},
    )
    assert len((await api.get(f"/trips/{trip['id']}")).json()["visits"]) == 1
    gone = await api.delete(f"/trips/{trip['id']}/blocks/{block_id}")
    assert gone.status_code == 200, gone.text
    assert titles(gone.json(), 1) == []
    assert (await api.get(f"/trips/{trip['id']}")).json()["visits"] == []


async def test_every_visit_is_in_the_itinerary_also_those_of_the_old_code(api, schema) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    ghent = await place(api, GHENT)
    bruges = await place(api, BRUGES)
    await api.post(
        f"/trips/{trip['id']}/visits", json={"place_id": ghent["id"], "visited_on": "2025-04-11"}
    )
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        await connection.execute(
            text(
                "insert into travel.travel_visit (trip_id, place_id, visited_on) "
                "values (:trip, :place, '2025-04-12')"
            ),
            {"trip": trip["id"], "place": bruges["id"]},
        )
        made = await itinerary.ensure_blocks(connection)

    found = await days(api, trip["id"])
    assert made == 1
    assert titles(found, 2) == ["Gante"]
    assert titles(found, 3) == ["Brujas"]


async def test_saved_without_a_day_and_nothing_outside_the_trip(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    same = str(uuid4())
    await block(api, trip["id"], id=same, title="Museo Groeninge")
    again = await block(api, trip["id"], id=same, title="Museo Groeninge")
    outside = await api.post(
        f"/trips/{trip['id']}/blocks", json={"title": "Tarde", "day": "2025-05-01"}
    )

    assert [b["title"] for b in again["unscheduled"]] == ["Museo Groeninge"]
    assert outside.status_code == 409


async def test_moving_a_plan_moves_its_blocks(api) -> None:
    trip = await make_trip(api, "Flandes", "2027-04-10", "2027-04-12", status="plan")
    await block(api, trip["id"], title="Paseo", day="2027-04-11")

    body = {"title": "Flandes", "starts_on": "2027-05-10", "ends_on": "2027-05-12"}
    moved = await api.put(f"/trips/{trip['id']}?shift=true", json=body)
    found = await days(api, trip["id"])

    assert moved.status_code == 200, moved.text
    assert titles(found, 2) == ["Paseo"]
    assert found["days"][1]["day"] == "2027-05-11"


async def test_claude_plans_a_day_with_the_tools(api) -> None:
    write = {"x-arga-scopes": "travel:read travel:write"}
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")

    added = await api.post(
        "/tools/add_block",
        json={
            "trip_id": trip["id"],
            "title": "Campanario",
            "day": "2025-04-10",
            "starts_at": "11:00",
            "place": BRUGES,
        },
        headers=write,
    )
    content = added.json()["content"]
    block_id = content["itinerary"]["days"][0]["items"][0]["block_id"]
    moved = await api.post(
        "/tools/move_block", json={"block_id": block_id, "day": None}, headers=write
    )
    read = await api.post(
        "/tools/get_trip",
        json={"trip_id": trip["id"], "include": ["itinerary"]},
        headers={"x-arga-scopes": "travel:read"},
    )

    assert added.status_code == 200, added.text
    assert content["itinerary"]["days"][0]["items"][0]["starts_at"] == "11:00"
    assert moved.json()["content"]["itinerary"]["unscheduled"][0]["title"] == "Campanario"
    assert read.json()["content"]["itinerary"]["unscheduled"][0]["place"]["name"] == "Brujas"
