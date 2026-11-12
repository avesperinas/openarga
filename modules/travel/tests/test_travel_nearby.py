from __future__ import annotations

from travel_kit import make_trip, place

WRITE = {"x-arga-scopes": "travel:read travel:write"}
READ = {"x-arga-scopes": "travel:read"}
HOTEL = {"name": "Hotel en Gion", "lat": 35.0037, "lon": 135.7788, "osm_type": "node", "osm_id": 7}
TEMPLE = {
    "type": "node",
    "id": 99,
    "lat": 35.0040,
    "lon": 135.7789,
    "tags": {"name": "八坂神社", "name:es": "Santuario Yasaka", "amenity": "place_of_worship"},
}


async def test_claude_finds_what_is_near_the_hotel_and_keeps_it_for_later(api, hub) -> None:
    hub.near = [TEMPLE]
    trip = await make_trip(api, "Japón", "2027-04-01", "2027-04-04", status="plan")
    hotel = await place(api, HOTEL)

    found = await api.post(
        "/tools/find_nearby", json={"place_id": hotel["id"], "radius": 500}, headers=READ
    )
    [candidate] = found.json()["content"]["candidates"]
    kept = await api.post(
        "/tools/add_block",
        json={"trip_id": trip["id"], "title": candidate["name"], "place": candidate},
        headers=WRITE,
    )

    assert found.status_code == 200, found.text
    assert (candidate["name"], candidate["local_name"], candidate["country_code"]) == (
        "Santuario Yasaka",
        "八坂神社",
        "JP",
    )
    assert 0 < candidate["distance_m"] < 100
    saved = kept.json()["content"]["itinerary"]["unscheduled"]
    assert [(b["title"], b["place"]["country"]) for b in saved] == [("Santuario Yasaka", "JP")]


async def test_the_app_asks_by_a_point_and_a_wrong_place_is_said(api, hub) -> None:
    hub.near = [TEMPLE]

    near = await api.get("/nearby", params={"lat": 35.0037, "lon": 135.7788, "kind": "sights"})
    lost = await api.post(
        "/tools/find_nearby",
        json={"place_id": "00000000-0000-4000-8000-000000000000"},
        headers=READ,
    )

    assert near.status_code == 200, near.text
    assert [p["name"] for p in near.json()["places"]] == ["Santuario Yasaka"]
    assert near.json()["failed"] is None
    assert lost.json()["content"]["code"] == "NOT_FOUND"
    assert hub.nearby_asked == 1
