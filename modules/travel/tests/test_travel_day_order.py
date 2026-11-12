from __future__ import annotations

from test_travel_tools import content
from travel_kit import BRUGES, GHENT, make_trip, place


async def last_day_of_flanders(api) -> tuple[str, dict]:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    bruges = await place(api, BRUGES)
    ghent = await place(api, GHENT)
    made = await api.post(
        f"/trips/{trip['id']}/stays",
        json={
            "place_id": bruges["id"],
            "arrives_on": "2025-04-10",
            "leaves_on": "2025-04-12",
            "check_out_at": "11:00",
        },
    )
    assert made.status_code == 201, made.text
    made = await api.post(
        f"/trips/{trip['id']}/legs",
        json={
            "from_place_id": bruges["id"],
            "to_place_id": ghent["id"],
            "mode": "plane",
            "travelled_on": "2025-04-12",
            "departs_at": "18:00",
            "arrives_at": "19:00",
        },
    )
    assert made.status_code == 201, made.text
    for body in (
        {"title": "Shopping", "starts_at": "09:30"},
        {"title": "Paseo"},
        {"title": "Comida", "kind": "meal", "starts_at": "13:00"},
    ):
        made = await api.post(f"/trips/{trip['id']}/blocks", json={"day": "2025-04-12", **body})
        assert made.status_code == 201, made.text
    return trip["id"], made.json()


def order(day: dict) -> list[str]:
    return [
        item["block"]["title"] if item["type"] == "block" else item["type"] for item in day["items"]
    ]


async def test_what_has_a_time_goes_in_the_order_of_the_clock(api) -> None:
    _, found = await last_day_of_flanders(api)

    assert order(found["days"][2]) == ["Shopping", "check_out", "Comida", "Paseo", "leg"]


async def test_the_tool_reads_the_day_in_the_same_order_with_its_times(api) -> None:
    trip_id, _ = await last_day_of_flanders(api)

    found = (await content(api, "get_trip", {**{"trip_id": trip_id}, "include": ["itinerary"]}))[
        "itinerary"
    ]
    items = found["days"][2]["items"]

    assert [(one["type"], one["starts_at"]) for one in items] == [
        ("block", "09:30"),
        ("check_out", "11:00"),
        ("block", "13:00"),
        ("block", None),
        ("leg", "18:00"),
    ]


async def test_a_day_has_a_title_until_it_is_emptied(api) -> None:
    trip_id, _ = await last_day_of_flanders(api)

    titled = await content(
        api, "update_day", {"trip_id": trip_id, "day": "2025-04-11", "title": "  Gante  en tren "}
    )
    from_app = (await api.get(f"/trips/{trip_id}/days")).json()
    emptied = await api.put(f"/trips/{trip_id}/days/2025-04-11/title", json={"title": ""})

    assert titled["itinerary"]["days"][1]["title"] == "Gante en tren"
    assert from_app["days"][1]["title"] == "Gante en tren"
    assert emptied.status_code == 200, emptied.text
    assert emptied.json()["days"][1]["title"] is None


async def test_a_title_outside_the_trip_is_refused(api) -> None:
    trip_id, _ = await last_day_of_flanders(api)

    refused = await api.put(f"/trips/{trip_id}/days/2025-04-20/title", json={"title": "Fuera"})

    assert refused.status_code == 409, refused.text
    assert "fuera del viaje" in refused.json()["detail"]


async def test_moving_the_trip_takes_the_titles_with_it(api) -> None:
    trip_id, _ = await last_day_of_flanders(api)
    for day, title in (("2025-04-10", "Llegada"), ("2025-04-11", "Gante")):
        await api.put(f"/trips/{trip_id}/days/{day}/title", json={"title": title})

    moved = await content(
        api,
        "update_trip",
        {
            "trip_id": trip_id,
            "starts_on": "2025-04-11",
            "ends_on": "2025-04-13",
            "shift_dates": True,
        },
    )
    found = (await content(api, "get_trip", {**{"trip_id": trip_id}, "include": ["itinerary"]}))[
        "itinerary"
    ]

    assert moved["trip"]["starts_on"] == "2025-04-11"
    assert [day["title"] for day in found["days"]] == ["Llegada", "Gante", None]


async def test_who_paid_is_said_by_name(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12", travellers=2)
    await content(
        api,
        "record_trip_expense",
        {
            "trip_id": trip["id"],
            "category": "other",
            "concept": "Museo",
            "amount": "30",
            "currency": "EUR",
            "paid_by": "yo",
        },
    )

    found = await content(api, "get_trip", {"trip_id": trip["id"]})

    paid_by = found["expenses"][0]["paid"]["paid_by"]
    assert paid_by is not None
    assert "-" not in paid_by
