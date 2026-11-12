from __future__ import annotations

from datetime import timedelta

from travel_kit import BRUGES, GHENT, make_trip, place

from travel import travel

READ = {"x-arga-scopes": "travel:read"}


def iso(days: int) -> str:
    return (travel.today() + timedelta(days=days)).isoformat()


async def test_today_is_the_day_of_the_trip_in_order_with_how_to_get_there(api) -> None:
    trip = await make_trip(api, "Flandes", iso(-1), iso(1))
    bruges = await place(api, BRUGES)
    ghent = await place(api, GHENT)
    await api.post(
        f"/trips/{trip['id']}/stays",
        json={
            "place_id": bruges["id"],
            "arrives_on": iso(-1),
            "leaves_on": iso(0),
            "accommodation": "Hotel Navarra",
            "check_out_at": "11:00",
        },
    )
    await api.post(
        f"/trips/{trip['id']}/stays",
        json={
            "place_id": ghent["id"],
            "arrives_on": iso(0),
            "leaves_on": iso(1),
            "check_in_at": "15:00",
        },
    )
    await api.post(
        f"/trips/{trip['id']}/legs",
        json={
            "from_place_id": bruges["id"],
            "to_place_id": ghent["id"],
            "mode": "train",
            "travelled_on": iso(0),
            "departs_at": "12:05",
            "carrier": "SNCB",
            "seat": "42",
        },
    )
    await api.post(
        f"/trips/{trip['id']}/blocks",
        json={
            "title": "Castillo de los Condes",
            "day": iso(0),
            "starts_at": "16:30",
            "place_id": ghent["id"],
        },
    )

    found = (await api.get("/today", params={"day": iso(0)})).json()

    assert (found["trip"]["title"], found["trip"]["number"], found["trip"]["days"]) == (
        "Flandes",
        2,
        3,
    )
    assert found["sleeping"] == "Gante"
    assert [(e["type"], e["title"], e["starts_at"]) for e in found["entries"]] == [
        ("check_out", "Sales de Hotel Navarra", "11:00:00"),
        ("leg", "Brujas → Gante", "12:05:00"),
        ("check_in", "Llegas a Gante", "15:00:00"),
        ("block", "Castillo de los Condes", "16:30:00"),
    ]
    leg = found["entries"][1]
    assert leg["detail"] == "SNCB · asiento 42"
    assert "travelmode=transit" in leg["where"]["google"]
    castle = found["entries"][3]["where"]
    assert castle["google"].startswith("https://www.google.com/maps/dir/?api=1&destination=51.")
    assert castle["apple"].startswith("https://maps.apple.com/?daddr=51.")


async def test_a_plan_is_not_today_and_without_a_trip_the_next_one_is_said(api) -> None:
    await make_trip(api, "Plan", iso(-1), iso(1), status="plan")
    await make_trip(api, "Roma", iso(10), iso(14))

    found = (await api.get("/today")).json()
    told = await api.post("/tools/get_today", json={}, headers=READ)

    assert found["trip"] is None
    assert found["next_trip"]["title"] == "Roma"
    content = told.json()["content"]
    assert (content["trip"], content["next_trip"]["days_to_go"]) == (None, 10)


async def test_today_goes_by_the_clock_and_what_has_no_time_stays_after_the_one_before(api) -> None:
    trip = await make_trip(api, "Lisboa", iso(-1), iso(1))
    bruges = await place(api, BRUGES)
    await api.post(
        f"/trips/{trip['id']}/stays",
        json={
            "place_id": bruges["id"],
            "arrives_on": iso(0),
            "leaves_on": iso(1),
            "check_in_at": "16:00",
        },
    )
    for title, starts in (("Palacio", "12:30"), ("Cena", "20:30"), ("Paseo", None)):
        made = await api.post(
            f"/trips/{trip['id']}/blocks",
            json={"title": title, "day": iso(0), "starts_at": starts},
        )
    walk = next(
        item["block"]["id"]
        for item in made.json()["days"][1]["items"]
        if item["block"] and item["block"]["title"] == "Paseo"
    )
    await api.put(
        f"/trips/{trip['id']}/blocks/{walk}/position", json={"day": iso(0), "position": 1}
    )

    found = (await api.get("/today", params={"day": iso(0)})).json()

    assert [e["title"] for e in found["entries"]] == [
        "Palacio",
        "Paseo",
        "Llegas a Brujas",
        "Cena",
    ]
