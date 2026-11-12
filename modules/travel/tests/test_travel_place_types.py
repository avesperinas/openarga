from __future__ import annotations

from sqlalchemy import text
from test_travel_tools import content
from travel_kit import make_trip, place

from travel.db import engine

PARLIAMENT = {
    "name": "Parlamento",
    "lat": 47.507,
    "lon": 19.0456,
    "kind": "attraction",
    "osm_type": "way",
    "osm_id": 24170580,
}
BEACH = {"name": "Glyfada", "lat": 39.6239, "lon": 19.8306, "kind": "beach"}


def activities(itinerary: dict, number: int) -> list[dict]:
    return [item for item in itinerary["days"][number - 1]["items"] if item.get("type") == "block"]


async def test_a_place_takes_its_type_from_openstreetmap_or_the_one_given(api) -> None:
    deduced = await place(api, PARLIAMENT)
    given = await place(api, {**BEACH, "category": "viewpoint"})
    unknown = await place(api, {"name": "Casa de Ana"})

    assert deduced["category"] == "culture"
    assert given["category"] == "viewpoint"
    assert unknown["category"] is None


async def test_the_type_changes_for_every_trip_and_the_tool_reads_it(api) -> None:
    saved = await place(api, BEACH)

    changed = await api.put(f"/places/{saved['id']}/category", json={"category": "nature"})
    told = await content(
        api, "update_place", {"place_id": saved["id"], "category": "beach", "dry_run": False}
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["category"] == "nature"
    assert told["place"]["category"] == "beach"


async def test_an_activity_added_by_claude_where_a_visit_already_is_comes_out_once(api) -> None:
    trip = await make_trip(api, "Budapest", "2027-11-11", "2027-11-14")
    await content(
        api,
        "add_visit",
        {"trip_id": trip["id"], "place": PARLIAMENT, "visited_on": "2027-11-12"},
    )

    found = await content(
        api,
        "add_block",
        {
            "trip_id": trip["id"],
            "title": "Visita guiada al Parlamento",
            "day": "2027-11-12",
            "starts_at": "10:00",
            "place": PARLIAMENT,
            "notes": "Tour en español",
        },
    )

    [one] = activities(found["itinerary"], 2)
    assert (one["title"], one["starts_at"], one["notes"]) == (
        "Visita guiada al Parlamento",
        "10:00",
        "Tour en español",
    )
    assert one["place"]["category"] == "culture"
    trip_now = await content(api, "get_trip", {"trip_id": trip["id"]})
    assert len(trip_now["visits"]) == 1


async def test_a_visit_after_the_activity_is_the_same_visit(api) -> None:
    trip = await make_trip(api, "Budapest", "2027-11-11", "2027-11-14")
    await content(
        api,
        "add_block",
        {
            "trip_id": trip["id"],
            "title": "Parlamento",
            "day": "2027-11-12",
            "starts_at": "10:00",
            "place": PARLIAMENT,
        },
    )

    await content(
        api, "add_visit", {"trip_id": trip["id"], "place": PARLIAMENT, "visited_on": "2027-11-12"}
    )
    found = (await content(api, "get_trip", {**{"trip_id": trip["id"]}, "include": ["itinerary"]}))[
        "itinerary"
    ]

    assert [one["title"] for one in activities(found, 2)] == ["Parlamento"]


async def test_what_was_already_twice_is_merged_on_the_next_change(api) -> None:
    trip = await make_trip(api, "Budapest", "2027-11-11", "2027-11-14")
    parliament = await place(api, PARLIAMENT)
    made = await api.post(
        f"/trips/{trip['id']}/blocks",
        json={
            "title": "Parlamento",
            "day": "2027-11-12",
            "place_id": parliament["id"],
            "starts_at": "10:00",
        },
    )
    assert made.status_code == 201, made.text
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        visit = await connection.scalar(
            text("""
                insert into travel.travel_visit (trip_id, place_id, visited_on)
                values (:trip, :place, '2027-11-12') returning id
            """),
            {"trip": trip["id"], "place": parliament["id"]},
        )
        await connection.execute(
            text("""
                insert into travel.travel_block (trip_id, day, position, kind, title, place_id,
                                                 visit_id, notes)
                values (:trip, '2027-11-12', 5, 'activity', 'Parlamento', :place, :visit,
                        'Llegar 30 min antes')
            """),
            {"trip": trip["id"], "place": parliament["id"], "visit": visit},
        )

    await api.put(f"/trips/{trip['id']}/days/2027-11-11/title", json={"title": "Llegada"})
    found = (await api.get(f"/trips/{trip['id']}/days")).json()
    blocks = [item["block"] for item in found["days"][1]["items"] if item["block"]]

    assert [(b["title"], b["starts_at"], b["notes"]) for b in blocks] == [
        ("Parlamento", "10:00:00", "Llegar 30 min antes")
    ]
