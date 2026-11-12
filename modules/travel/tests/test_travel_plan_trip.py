from __future__ import annotations

from test_travel_tools import content

BILBAO = {"name": "Bilbao", "lat": 43.263, "lon": -2.935, "country_code": "ES"}
BUDAPEST = {"name": "Budapest", "lat": 47.4979, "lon": 19.0402, "country_code": "HU"}


def spot(name: str, lat: float, category: str) -> dict:
    return {"name": name, "lat": lat, "lon": 19.05, "country_code": "HU", "category": category}


def four_days() -> dict:
    days = []
    for number in range(4):
        day = f"2027-11-{11 + number}"
        days.append(
            {
                "day": day,
                "title": f"Día {number + 1} en Budapest",
                "blocks": [
                    {
                        "title": f"Visita {number}-{index}",
                        "starts_at": f"{9 + index * 2:02d}:00",
                        "place": spot(f"Sitio {number}-{index}", 47.49 + index / 1000, "culture"),
                    }
                    for index in range(5)
                ],
            }
        )
    return {
        "title": "Budapest",
        "starts_on": "2027-11-11",
        "ends_on": "2027-11-14",
        "travellers": 2,
        "companions": ["Luis"],
        "summary": "Cuatro días de termas y Danubio.",
        "stays": [
            {
                "place": BUDAPEST,
                "arrives_on": "2027-11-11",
                "leaves_on": "2027-11-14",
                "accommodation": "Hotel del centro",
                "check_in_at": "15:00",
                "cost_eur": "486",
                "paid_by": "yo",
            }
        ],
        "legs": [
            {
                "mode": "plane",
                "from_place": BILBAO,
                "to_place": BUDAPEST,
                "travelled_on": "2027-11-11",
                "departs_at": "06:05",
                "cost_eur": "412",
                "paid_by": "Luis",
            },
            {
                "mode": "plane",
                "from_place": BUDAPEST,
                "to_place": BILBAO,
                "travelled_on": "2027-11-14",
                "departs_at": "18:00",
                "same_ticket_as": 0,
            },
        ],
        "days": days,
        "saved": [{"title": "New York Café", "place": spot("New York Café", 47.498, "cafe")}],
    }


async def test_claude_plans_four_days_with_twenty_blocks_in_one_call(api) -> None:
    made = await content(api, "plan_trip", four_days())

    assert made["created_trip"] is True
    assert made["added"] == {"stays": 1, "legs": 2, "day_titles": 4, "blocks": 20, "saved": 1}
    days = made["itinerary"]["days"]
    assert [day["title"] for day in days] == [f"Día {n} en Budapest" for n in range(1, 5)]
    assert sum(1 for day in days for item in day["items"] if item["type"] == "block") == 20
    assert made["itinerary"]["unscheduled"][0]["place"]["category"] == "cafe"
    bookings = (
        await content(
            api, "get_trip", {**{"trip_id": made["trip"]["trip_id"]}, "include": ["bookings"]}
        )
    )["bookings"]
    back = next(one for one in bookings["bookings"] if one.get("same_ticket_as"))
    assert back["same_ticket_as"]["route"] == "Bilbao → Budapest"


async def test_a_day_outside_the_trip_saves_nothing_and_says_which(api) -> None:
    plan = four_days()
    plan["days"][2]["day"] = "2027-11-20"

    refused = await content(api, "plan_trip", plan)
    trips = await content(api, "get_trips", {"include_archived": True})

    assert refused["code"] == "DATE_OUT_OF_RANGE"
    assert refused["error"].startswith("days[2]")
    assert trips["trips"] == []


async def test_the_rehearsal_shows_the_itinerary_and_keeps_nothing(api) -> None:
    rehearsed = await content(api, "plan_trip", {**four_days(), "dry_run": True})
    trips = await content(api, "get_trips", {"include_archived": True})

    assert rehearsed["dry_run"] is True
    assert rehearsed["added"]["blocks"] == 20
    assert trips["trips"] == []
