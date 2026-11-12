from __future__ import annotations

from test_travel_tools import content

BILBAO = {"name": "Bilbao", "lat": 43.263, "lon": -2.935}
BUDAPEST = {"name": "Budapest", "lat": 47.4979, "lon": 19.0402}


async def budapest(api) -> tuple[str, str, str]:
    created = await content(
        api,
        "create_trip",
        {
            "title": "Budapest",
            "starts_on": "2027-11-11",
            "ends_on": "2027-11-14",
            "travellers": 2,
            "companions": ["Luis"],
            "status": "plan",
        },
    )
    trip_id = created["trip"]["trip_id"]
    out = await content(
        api,
        "add_leg",
        {
            "trip_id": trip_id,
            "from_place": BILBAO,
            "to_place": BUDAPEST,
            "mode": "plane",
            "travelled_on": "2027-11-11",
            "departs_at": "06:05",
            "carrier": "Lufthansa",
            "number": "LH1825 vía Fráncfort (LH1338)",
            "seat": "18A, 18B, 18C, 18D, 19A, 19B",
            "terminal": "Terminal 2B Schengen",
            "confirmation": "7HQX2L",
            "cost_eur": "412",
            "paid_by": "Luis",
        },
    )
    leg_out = out["trip"]["legs"][0]["leg_id"]
    back = await content(
        api,
        "add_leg",
        {
            "trip_id": trip_id,
            "from_place": BUDAPEST,
            "to_place": BILBAO,
            "mode": "plane",
            "travelled_on": "2027-11-14",
            "departs_at": "18:00",
            "ticket_leg_id": leg_out,
        },
    )
    leg_back = next(one for one in back["trip"]["legs"] if one["leg_id"] != leg_out)["leg_id"]
    return trip_id, leg_out, leg_back


async def test_a_return_ticket_is_one_expense_shown_on_both_legs(api) -> None:
    trip_id, leg_out, leg_back = await budapest(api)

    found = (await content(api, "get_trip", {**{"trip_id": trip_id}, "include": ["bookings"]}))[
        "bookings"
    ]
    trip = await content(api, "get_trip", {"trip_id": trip_id})
    legs = {one["leg_id"]: one for one in found["bookings"]}

    assert [(e["concept"], e["paid"]["total_eur"]) for e in trip["expenses"]] == [
        ("Vuelo Lufthansa LH1825 vía Fráncfort (LH1338)", 412.0)
    ]
    assert legs[leg_out]["cost_eur"] == 412.0
    assert legs[leg_out]["paid_by"] == "Luis"
    assert legs[leg_back]["confirmation"] == "7HQX2L"
    assert legs[leg_back]["booked"] is True
    assert legs[leg_back]["same_ticket_as"] == {"leg_id": leg_out, "route": "Bilbao → Budapest"}
    assert found["pending"] == 0


async def test_who_paid_a_booking_counts_in_the_balance(api) -> None:
    trip_id, _, _ = await budapest(api)

    balance = (await content(api, "get_trip", {**{"trip_id": trip_id}, "include": ["balance"]}))[
        "balance"
    ]

    people = {one["traveller"]: one for one in balance["people"]}
    assert people["Luis"]["paid_eur"] == 412.0
    assert balance["unassigned_eur"] == 0.0


async def test_who_paid_without_a_cost_is_refused(api) -> None:
    created = await content(
        api,
        "create_trip",
        {"title": "Lisboa", "starts_on": "2027-05-01", "ends_on": "2027-05-03"},
    )

    refused = await api.post(
        "/tools/add_leg",
        json={
            "trip_id": created["trip"]["trip_id"],
            "from_place": BILBAO,
            "to_place": BUDAPEST,
            "mode": "plane",
            "travelled_on": "2027-05-01",
            "paid_by": "yo",
        },
        headers={"x-arga-scopes": "travel:read travel:write"},
    )

    assert "falta cost_eur" in refused.text


async def test_a_ticket_cannot_ride_on_one_that_rides_on_another(api) -> None:
    trip_id, _, leg_back = await budapest(api)

    refused = await api.post(
        "/tools/add_leg",
        json={
            "trip_id": trip_id,
            "from_place": BUDAPEST,
            "to_place": BILBAO,
            "mode": "plane",
            "travelled_on": "2027-11-14",
            "ticket_leg_id": leg_back,
        },
        headers={"x-arga-scopes": "travel:read travel:write"},
    )

    assert "apunta al que lleva el billete" in refused.text
