from __future__ import annotations

from travel_kit import BRUGES, GHENT, make_trip, place

WRITE = {"x-arga-scopes": "travel:read travel:write"}


async def test_a_flight_with_its_ticket_and_price_is_a_booking_and_an_expense(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12", travellers=2)
    bruges = await place(api, BRUGES)
    ghent = await place(api, GHENT)

    saved = await api.post(
        f"/trips/{trip['id']}/legs",
        json={
            "from_place_id": bruges["id"],
            "to_place_id": ghent["id"],
            "mode": "plane",
            "travelled_on": "2025-04-10",
            "departs_at": "07:15",
            "arrives_on": "2025-04-10",
            "arrives_at": "09:40",
            "carrier": "Iberia",
            "number": "IB3166",
            "seat": "14C",
            "confirmation": "ABC123",
            "cost_eur": "240.00",
        },
    )
    leg = saved.json()["legs"][0]
    expenses = saved.json()["expenses"]
    listed = (await api.get(f"/trips/{trip['id']}/bookings")).json()

    assert saved.status_code == 201, saved.text
    assert (leg["number"], leg["seat"], leg["confirmation"]) == ("IB3166", "14C", "ABC123")
    assert leg["cost_eur"] == 240.0
    assert [(e["concept"], e["amount_eur"], e["leg_id"]) for e in expenses] == [
        ("Vuelo Iberia IB3166", 120.0, leg["id"])
    ]
    assert [(b["type"], b["booked"], b["at"]) for b in listed] == [("leg", True, "07:15:00")]


async def test_editing_without_the_booking_keeps_it_and_null_cost_takes_the_expense(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    bruges = await place(api, BRUGES)
    made = await api.post(
        f"/trips/{trip['id']}/stays",
        json={
            "place_id": bruges["id"],
            "arrives_on": "2025-04-10",
            "leaves_on": "2025-04-12",
            "accommodation": "Hotel Navarra",
            "check_in_at": "15:00",
            "confirmation": "XYZ",
            "cost_eur": "300",
        },
    )
    stay = made.json()["stays"][0]

    kept = await api.put(
        f"/trips/{trip['id']}/stays/{stay['id']}",
        json={"place_id": bruges["id"], "arrives_on": "2025-04-10", "leaves_on": "2025-04-12"},
    )
    cleared = await api.put(
        f"/trips/{trip['id']}/stays/{stay['id']}",
        json={
            "place_id": bruges["id"],
            "arrives_on": "2025-04-10",
            "leaves_on": "2025-04-12",
            "cost_eur": None,
        },
    )

    assert made.json()["expenses"][0]["concept"] == "Hotel Navarra"
    assert (kept.json()["stays"][0]["confirmation"], kept.json()["stays"][0]["cost_eur"]) == (
        "XYZ",
        300.0,
    )
    assert cleared.json()["expenses"] == []
    assert cleared.json()["stays"][0]["confirmation"] == "XYZ"


async def test_removing_a_booking_keeps_what_was_paid(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    bruges = await place(api, BRUGES)
    made = await api.post(
        f"/trips/{trip['id']}/stays",
        json={
            "place_id": bruges["id"],
            "arrives_on": "2025-04-10",
            "leaves_on": "2025-04-12",
            "cost_eur": "90",
        },
    )
    stay_id = made.json()["stays"][0]["id"]

    gone = await api.delete(f"/trips/{trip['id']}/stays/{stay_id}")

    assert gone.status_code == 200, gone.text
    assert [(e["amount_eur"], e.get("stay_id")) for e in gone.json()["expenses"]] == [(90.0, None)]


async def test_what_is_not_booked_yet_is_said(api) -> None:
    trip = await make_trip(api, "Japón", "2027-04-01", "2027-04-04", status="plan")
    bruges = await place(api, BRUGES)
    await api.post(
        f"/trips/{trip['id']}/stays",
        json={"place_id": bruges["id"], "arrives_on": "2027-04-01", "leaves_on": "2027-04-04"},
    )
    await api.post(
        f"/trips/{trip['id']}/blocks",
        json={"title": "Paseo", "day": "2027-04-02"},
    )
    await api.post(
        f"/trips/{trip['id']}/blocks",
        json={"title": "Museo Ghibli", "day": "2027-04-02", "confirmation": "GH-1"},
    )

    answer = await api.post(
        "/tools/get_trip", json={"trip_id": trip["id"], "include": ["bookings"]}, headers=WRITE
    )
    content = answer.json()["content"]["bookings"]

    assert answer.status_code == 200, answer.text
    assert content["pending"] == 1
    assert [(b["type"], b["title"], b["booked"]) for b in content["bookings"]] == [
        ("stay", "Brujas", False),
        ("block", "Museo Ghibli", True),
    ]


async def test_claude_adds_a_train_ticket_and_then_only_the_seat(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    added = await api.post(
        "/tools/add_leg",
        json={
            "trip_id": trip["id"],
            "mode": "train",
            "from_place": BRUGES,
            "to_place": GHENT,
            "travelled_on": "2025-04-11",
            "carrier": "SNCB",
            "departs_at": "10:05",
            "cost_eur": "18.40",
        },
        headers=WRITE,
    )
    leg = added.json()["content"]["trip"]["legs"][0]
    seat = await api.post(
        "/tools/update_leg", json={"leg_id": leg["leg_id"], "seat": "42"}, headers=WRITE
    )
    after = seat.json()["content"]["trip"]

    assert added.status_code == 200, added.text
    assert (leg["carrier"], leg["departs_at"], leg["cost_eur"]) == ("SNCB", "10:05", 18.4)
    assert after["legs"][0]["seat"] == "42" and after["legs"][0]["carrier"] == "SNCB"
    assert [e["amount_eur_per_person"] for e in after["expenses"]] == [18.4]
