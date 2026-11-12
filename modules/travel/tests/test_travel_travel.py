from __future__ import annotations

from travel_kit import BRUGES, GHENT, LILLE, MADRID, SEVILLE, make_trip, place, stay


async def test_a_trip_with_three_stays_found_by_name_keeps_their_iso_codes(api) -> None:
    trip = await make_trip(api, travellers=2, companions=["Ane"], tags=["escapada"])
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")
    await stay(api, trip["id"], GHENT, "2025-04-12", "2025-04-14")
    done = await stay(api, trip["id"], LILLE, "2025-04-14", "2025-04-15")

    assert [
        (s["place"]["name"], s["place"]["country_code"], s["place"]["region_code"])
        for s in done["stays"]
    ] == [
        ("Brujas", "BE", "BE-VLG"),
        ("Gante", "BE", "BE-VLG"),
        ("Lille", "FR", "FR-HDF"),
    ]
    assert [s["nights"] for s in done["stays"]] == [2, 2, 1]
    assert done["countries"] == ["BE", "FR"]
    assert (done["nights"], done["days"]) == (5, 6)
    assert done["stays"][2]["place"]["region"] == "Hauts-de-France"


async def test_the_same_openstreetmap_place_is_saved_once(api) -> None:
    first = await place(api, BRUGES)
    again = await place(api, {**BRUGES, "name": "Bruges"})

    assert again["id"] == first["id"]
    assert len((await api.get("/places", params={"query": "bru"})).json()) == 1


async def test_a_place_typed_without_coordinates_is_kept_unresolved(api) -> None:
    found = await place(api, {"name": "Casa rural de los abuelos"})

    assert (found["lat"], found["country_code"], found["region_code"]) == (None, None, None)


async def test_what_hangs_from_a_trip_falls_within_its_dates(api) -> None:
    trip = await make_trip(api)
    bruges = await place(api, BRUGES)

    outside = await api.post(
        f"/trips/{trip['id']}/stays",
        json={"place_id": bruges["id"], "arrives_on": "2025-04-09", "leaves_on": "2025-04-11"},
    )
    backwards = await api.post(
        f"/trips/{trip['id']}/stays",
        json={"place_id": bruges["id"], "arrives_on": "2025-04-12", "leaves_on": "2025-04-11"},
    )

    assert outside.status_code == 409
    assert "fuera del viaje" in outside.json()["detail"]
    assert backwards.status_code == 422


async def test_legs_carry_their_mode_and_their_kilometres(api) -> None:
    trip = await make_trip(api, "Andalucía", "2024-10-01", "2024-10-05")
    madrid = await place(api, MADRID)
    seville = await place(api, SEVILLE)

    done = (
        await api.post(
            f"/trips/{trip['id']}/legs",
            json={
                "from_place_id": madrid["id"],
                "to_place_id": seville["id"],
                "mode": "train",
                "travelled_on": "2024-10-01",
            },
        )
    ).json()

    [leg] = done["legs"]
    assert leg["mode"] == "train"
    assert 450 < leg["km"] < 490
    assert done["km"] == leg["km"]


async def test_a_leg_says_whether_it_is_drawn_and_keeps_it_when_corrected(api) -> None:
    trip = await make_trip(api, "Andalucía", "2024-10-01", "2024-10-05")
    madrid = await place(api, MADRID)
    seville = await place(api, SEVILLE)
    leg = {"from_place_id": madrid["id"], "to_place_id": seville["id"], "mode": "train"}

    [added] = (await api.post(f"/trips/{trip['id']}/legs", json=leg)).json()["legs"]
    shown = await api.put(
        f"/trips/{trip['id']}/legs/{added['id']}", json={**leg, "mode": "car", "on_map": True}
    )
    hidden = await api.put(f"/trips/{trip['id']}/legs/{added['id']}", json={**leg, "on_map": False})

    assert added["on_map"] is None
    assert shown.status_code == 200, shown.text
    assert (shown.json()["legs"][0]["mode"], shown.json()["legs"][0]["on_map"]) == ("car", True)
    assert hidden.json()["legs"][0]["on_map"] is False


async def test_spend_is_per_person_and_per_day_like_in_the_sheet(api) -> None:
    trip = await make_trip(api, travellers=2)
    for category, concept, amount in (
        ("transport", "Vuelos", "120.50"),
        ("lodging", "Hotel", "180"),
        ("other", "Excursiones", "29.50"),
    ):
        response = await api.post(
            f"/trips/{trip['id']}/expenses",
            json={"category": category, "concept": concept, "amount_eur": amount},
        )
        assert response.status_code == 201, response.text

    spend = (await api.get(f"/trips/{trip['id']}")).json()["spend"]

    assert spend == {
        "per_person": 330.0,
        "group": 660.0,
        "per_day": 55.0,
        "by_category": {"transport": 120.5, "lodging": 180.0, "other": 29.5},
    }


async def test_a_stay_used_by_a_leg_is_not_removed_underneath_it(api) -> None:
    trip = await make_trip(api)
    done = await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")
    ghent = await place(api, GHENT)
    await api.post(
        f"/trips/{trip['id']}/legs",
        json={
            "from_place_id": done["stays"][0]["place"]["id"],
            "to_place_id": ghent["id"],
            "mode": "car",
        },
    )

    refused = await api.delete(f"/trips/{trip['id']}/stays/{done['stays'][0]['id']}")

    assert refused.status_code == 409


async def test_deleting_a_trip_takes_its_parts_but_keeps_the_places(api) -> None:
    trip = await make_trip(api)
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")

    assert (await api.delete(f"/trips/{trip['id']}")).status_code == 204
    assert (await api.get(f"/trips/{trip['id']}")).status_code == 404
    assert [p["name"] for p in (await api.get("/places")).json()] == ["Brujas"]


async def test_visits_paint_softly_and_stays_strongly(api) -> None:
    trip = await make_trip(api)
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-15")
    lille = await place(api, LILLE)
    await api.post(
        f"/trips/{trip['id']}/visits", json={"place_id": lille["id"], "visited_on": "2025-04-12"}
    )

    stats = (await api.get("/stats")).json()

    top = {area["code"]: (area["slept"], area["nights"]) for area in stats["top_countries"]}
    assert top == {"BE": (True, 5), "FR": (False, 0)}
    assert stats["europe_visited"] == ["BE", "FR"]
    assert stats["europe_total"] == 44
    assert stats["regions"] == 2


async def test_the_statistics_add_up_by_year_and_by_mode(api) -> None:
    first = await make_trip(api, "Flandes", "2024-04-10", "2024-04-13")
    second = await make_trip(api, "Madrid", "2025-02-01", "2025-02-03")
    await stay(api, first["id"], BRUGES, "2024-04-10", "2024-04-13")
    await stay(api, second["id"], MADRID, "2025-02-01", "2025-02-03")
    await api.post(
        f"/trips/{first['id']}/expenses",
        json={"category": "lodging", "concept": "Hotel", "amount_eur": "200"},
    )

    stats = (await api.get("/stats")).json()

    assert [(row["year"], row["trips"], row["nights"]) for row in stats["by_year"]] == [
        (2024, 1, 3),
        (2025, 1, 2),
    ]
    assert stats["cost_per_day"] == [
        {"trip_id": first["id"], "title": "Flandes", "starts_on": "2024-04-10", "per_day": 50.0}
    ]
    assert stats["average_cost_per_day"] == 50.0
    assert stats["spend_per_night_by_country"][0]["code"] == "BE"
    assert len(stats["nights_calendar"]) == 5


async def test_other_places_count_where_you_have_been_and_nothing_else(api) -> None:
    trip = await make_trip(api)
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")
    seville = await place(api, SEVILLE)

    added = await api.post("/others", json={"place_id": seville["id"], "note": "hacia 2005"})

    assert added.status_code == 201, added.text
    other = added.json()
    assert (other["place"]["country_code"], other["note"]) == ("ES", "hacia 2005")
    atlas = (await api.get("/atlas")).json()
    assert [one["place"]["name"] for one in atlas["others"]] == ["Sevilla"]
    stats = (await api.get("/stats")).json()
    assert (stats["trips"], stats["nights"], stats["countries"], stats["regions"]) == (1, 5, 2, 2)
    spain = next(area for area in stats["top_countries"] if area["code"] == "ES")
    assert (spain["slept"], spain["trips"], spain["first"]) == (False, 0, None)


async def test_the_same_other_place_twice_is_one_and_it_can_be_removed(api) -> None:
    seville = await place(api, SEVILLE)
    first = (
        await api.post("/others", json={"place_id": seville["id"], "note": "hacia 2005"})
    ).json()
    again = (await api.post("/others", json={"place_id": seville["id"]})).json()

    assert again["id"] == first["id"]
    assert again["note"] == "hacia 2005"
    assert len((await api.get("/atlas")).json()["others"]) == 1

    assert (await api.delete(f"/others/{first['id']}")).status_code == 204
    assert (await api.get("/atlas")).json()["others"] == []
    assert (await api.delete(f"/others/{first['id']}")).status_code == 404
    assert [one["id"] for one in (await api.get("/places")).json()] == [seville["id"]]


async def test_an_other_place_needs_a_place_that_exists(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    assert (await api.post("/others", json={"place_id": missing})).status_code == 404


async def test_an_archived_trip_still_counts_and_can_come_back(api) -> None:
    trip = await make_trip(api)
    await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12")
    assert trip["archived"] is False

    archived = await api.put(f"/trips/{trip['id']}/archived", json={"archived": True})

    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True
    assert [one["archived"] for one in (await api.get("/atlas")).json()["trips"]] == [True]
    stats = (await api.get("/stats")).json()
    assert (stats["trips"], stats["nights"], stats["countries"]) == (1, 5, 1)

    back = await api.put(f"/trips/{trip['id']}/archived", json={"archived": False})
    assert back.json()["archived"] is False
    assert len(back.json()["stays"]) == 1

    missing = "00000000-0000-4000-8000-000000000000"
    assert (await api.put(f"/trips/{missing}/archived", json={"archived": True})).status_code == 404


async def test_where_you_live_is_one_place_and_counts_for_nothing(api) -> None:
    assert (await api.get("/atlas")).json()["home"] is None
    madrid = await place(api, MADRID)
    seville = await place(api, SEVILLE)

    first = await api.put("/home", json={"place_id": madrid["id"]})
    assert first.status_code == 200, first.text
    assert first.json()["region_code"] == "ES-MD"
    moved = (await api.put("/home", json={"place_id": seville["id"]})).json()

    atlas = (await api.get("/atlas")).json()
    assert atlas["home"]["id"] == moved["id"] == seville["id"]
    stats = (await api.get("/stats")).json()
    assert (stats["countries"], stats["regions"]) == (0, 0)

    assert (await api.delete("/home")).status_code == 204
    assert (await api.get("/atlas")).json()["home"] is None


async def test_where_you_live_needs_a_place_that_exists(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    assert (await api.put("/home", json={"place_id": missing})).status_code == 404
