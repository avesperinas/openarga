from __future__ import annotations

from test_travel_tools import READ, WRITE, call, content

MADRID = {"name": "Madrid", "lat": 40.4168, "lon": -3.7038}
BRUGES = {"name": "Brujas", "lat": 51.2085, "lon": 3.2267}
GHENT = {"name": "Gante", "lat": 51.0543, "lon": 3.7174}
DAMME = {"name": "Damme", "lat": 51.2515, "lon": 3.2819}
LILLE = {"name": "Lille", "lat": 50.6292, "lon": 3.0573}
SEVILLE = {"name": "Sevilla", "lat": 37.389, "lon": -5.984}


async def flanders(api) -> dict:
    created = await content(
        api,
        "create_trip",
        {
            "title": "Flandes",
            "starts_on": "2025-03-07",
            "ends_on": "2025-03-11",
            "travellers": 2,
            "tags": ["escapada"],
            "notes": "con lluvia",
        },
    )
    trip_id = created["trip"]["trip_id"]
    bruges = await content(
        api,
        "add_stay",
        {
            "trip_id": trip_id,
            "place": BRUGES,
            "arrives_on": "2025-03-07",
            "leaves_on": "2025-03-09",
        },
    )
    bruges_id = bruges["trip"]["stays"][0]["stay_id"]
    ghent = await content(
        api,
        "add_stay",
        {"trip_id": trip_id, "place": GHENT, "arrives_on": "2025-03-09", "leaves_on": "2025-03-11"},
    )
    ghent_id = next(s["stay_id"] for s in ghent["trip"]["stays"] if s["name"] == "Gante")
    await content(
        api,
        "add_leg",
        {
            "trip_id": trip_id,
            "mode": "plane",
            "from_place": MADRID,
            "to_stay_id": bruges_id,
            "travelled_on": "2025-03-07",
        },
    )
    await content(
        api,
        "add_leg",
        {
            "trip_id": trip_id,
            "mode": "train",
            "from_stay_id": bruges_id,
            "to_stay_id": ghent_id,
            "travelled_on": "2025-03-09",
        },
    )
    await content(
        api, "add_visit", {"trip_id": trip_id, "place": DAMME, "visited_on": "2025-03-08"}
    )
    await content(
        api,
        "record_trip_expense",
        {
            "trip_id": trip_id,
            "category": "lodging",
            "concept": "Hotel",
            "amount_eur_per_person": "100",
        },
    )
    return await content(api, "get_trip", {"trip_id": trip_id}, READ)


async def test_every_piece_carries_the_id_the_tools_that_edit_it_ask_for(api) -> None:
    trip = await flanders(api)

    [plane, train] = trip["legs"]
    bruges, ghent = trip["stays"]
    [expense] = trip["expenses"]

    assert expense["expense_id"]
    assert (plane["from_stay_id"], plane["to_stay_id"]) == (None, bruges["stay_id"])
    assert (train["from_stay_id"], train["to_stay_id"]) == (bruges["stay_id"], ghent["stay_id"])
    assert (train["from_place_id"], train["to_place_id"]) == (bruges["place_id"], ghent["place_id"])
    assert plane["from_place_id"] and plane["from"] == "Madrid"


async def test_recording_an_expense_says_its_id(api) -> None:
    trip = await flanders(api)

    recorded = await content(
        api,
        "record_trip_expense",
        {
            "trip_id": trip["trip_id"],
            "category": "transport",
            "concept": "Vuelos",
            "amount_eur_per_person": "150",
        },
    )

    ids = [e["expense_id"] for e in recorded["trip"]["expenses"]]
    assert recorded["expense_id"] in ids
    assert recorded["spend"]["per_day_eur"] == 50.0


async def test_the_other_places_are_listed_with_their_ids(api) -> None:
    added = await content(api, "add_other_place", {"place": LILLE, "note": "de paso"})

    listed = await content(api, "get_travel", {}, READ)

    assert len(listed["other_places"]) == 1
    [one] = listed["other_places"]
    assert (one["other_place_id"], one["place_id"], one["note"]) == (
        added["other_place_id"],
        added["place_id"],
        "de paso",
    )


async def test_the_archived_trips_are_left_out_unless_asked_for(api) -> None:
    trip = await flanders(api)
    await content(api, "archive_trip", {"trip_id": trip["trip_id"]})

    default = await content(api, "get_trips", {}, READ)
    everything = await content(api, "get_trips", {"include_archived": True}, READ)
    visited = await content(api, "get_travel", {}, READ)

    assert default["total"] == 0
    assert [(t["title"], t["archived"]) for t in everything["trips"]] == [("Flandes", True)]
    assert [a["code"] for a in visited["areas"]] == ["BE"]

    back = await content(api, "unarchive_trip", {"trip_id": trip["trip_id"]})
    assert back["trip"]["archived"] is False
    assert (await content(api, "get_trips", {}, READ))["total"] == 1


async def test_updating_a_trip_touches_only_what_is_given(api) -> None:
    trip = await flanders(api)

    updated = await content(
        api,
        "update_trip",
        {"trip_id": trip["trip_id"], "title": "Flandes en marzo", "notes": None, "tags": ["frío"]},
    )

    after = updated["trip"]
    assert (after["title"], after["notes"], after["tags"]) == ("Flandes en marzo", None, ["frío"])
    assert (after["starts_on"], after["travellers"], len(after["stays"])) == ("2025-03-07", 2, 2)


async def test_longer_dates_redo_the_cost_per_day(api) -> None:
    trip = await flanders(api)
    assert trip["spend"]["per_day_eur"] == 20.0

    updated = await content(
        api, "update_trip", {"trip_id": trip["trip_id"], "ends_on": "2025-03-16"}
    )

    assert updated["trip"]["nights"] == 9
    assert updated["trip"]["spend"]["per_day_eur"] == 10.0


async def test_dates_that_leave_pieces_out_change_nothing_and_say_which(api) -> None:
    trip = await flanders(api)

    answer = await content(
        api, "update_trip", {"trip_id": trip["trip_id"], "ends_on": "2025-03-08", "title": "X"}
    )

    assert answer["code"] == "DATE_OUT_OF_RANGE"
    kinds = {(c["kind"], c["name"]) for c in answer["conflicts"]}
    assert kinds == {("stay", "Brujas"), ("stay", "Gante"), ("leg", "Brujas → Gante")}
    again = await content(api, "get_trip", {"trip_id": trip["trip_id"]}, READ)
    assert (again["title"], again["ends_on"]) == ("Flandes", "2025-03-11")


async def test_a_trip_that_ends_before_it_starts_is_refused(api) -> None:
    trip = await flanders(api)

    answer = await content(
        api, "update_trip", {"trip_id": trip["trip_id"], "starts_on": "2025-03-12"}
    )

    assert answer["code"] == "INVALID"
    assert "acabar antes de empezar" in answer["error"]


async def test_a_title_and_first_day_already_taken_is_a_duplicate(api) -> None:
    trip = await flanders(api)
    other = await content(
        api, "create_trip", {"title": "Oporto", "starts_on": "2025-03-07", "ends_on": "2025-03-09"}
    )

    answer = await content(api, "update_trip", {"trip_id": trip["trip_id"], "title": "oporto"})

    assert answer["code"] == "DUPLICATE_TRIP"
    assert answer["conflicts"] == [{"trip_id": other["trip"]["trip_id"]}]


async def test_keeping_the_group_total_redoes_the_amounts_per_person(api) -> None:
    trip = await flanders(api)
    assert (trip["spend"]["per_person_eur"], trip["spend"]["group_eur"]) == (100.0, 200.0)

    kept = await content(
        api,
        "update_trip",
        {"trip_id": trip["trip_id"], "travellers": 4, "keep_group_total": True},
    )
    plain = await content(api, "update_trip", {"trip_id": trip["trip_id"], "travellers": 5})

    assert (kept["trip"]["spend"]["per_person_eur"], kept["trip"]["spend"]["group_eur"]) == (
        50.0,
        200.0,
    )
    assert kept["trip"]["expenses"][0]["amount_eur_per_person"] == 50.0
    assert (plain["trip"]["spend"]["per_person_eur"], plain["trip"]["spend"]["group_eur"]) == (
        50.0,
        250.0,
    )


async def test_a_rehearsal_shows_the_result_and_writes_nothing(api) -> None:
    trip = await flanders(api)

    rehearsed = await content(
        api,
        "update_trip",
        {"trip_id": trip["trip_id"], "travellers": 4, "keep_group_total": True, "dry_run": True},
    )

    assert rehearsed["dry_run"] is True
    assert rehearsed["trip"]["expenses"][0]["amount_eur_per_person"] == 50.0
    again = await content(api, "get_trip", {"trip_id": trip["trip_id"]}, READ)
    assert (again["travellers"], again["expenses"][0]["amount_eur_per_person"]) == (2, 100.0)


async def test_a_trip_that_does_not_exist_is_not_found(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    answer = await content(api, "update_trip", {"trip_id": missing, "title": "X"})

    assert answer["code"] == "NOT_FOUND"


async def test_a_trip_is_not_deleted_if_the_title_does_not_match(api) -> None:
    trip = await flanders(api)

    answer = await content(api, "delete_trip", {"trip_id": trip["trip_id"], "title": "flandes"})

    assert answer["code"] == "TITLE_MISMATCH"
    assert "Flandes" in answer["error"]
    assert (await content(api, "get_trips", {}, READ))["total"] == 1


async def test_deleting_a_trip_rehearsed_counts_and_keeps_everything(api) -> None:
    trip = await flanders(api)

    rehearsed = await content(
        api, "delete_trip", {"trip_id": trip["trip_id"], "title": "Flandes", "dry_run": True}
    )

    assert rehearsed["dry_run"] is True
    assert rehearsed["deleted"] == {
        "trip_id": trip["trip_id"],
        "title": "Flandes",
        "stays": 2,
        "visits": 1,
        "legs": 2,
        "expenses": 1,
    }
    assert (await content(api, "get_trips", {}, READ))["total"] == 1


async def test_deleting_a_trip_takes_its_pieces_and_leaves_the_places(api) -> None:
    trip = await flanders(api)
    await content(api, "add_other_place", {"place": SEVILLE})

    deleted = await content(api, "delete_trip", {"trip_id": trip["trip_id"], "title": "Flandes"})

    assert deleted["deleted"]["legs"] == 2
    assert (await content(api, "get_trips", {"include_archived": True}, READ))["total"] == 0
    visited = await content(api, "get_travel", {}, READ)
    assert [a["code"] for a in visited["areas"]] == ["ES"]
    saved = await content(api, "find_place", {"query": "Brujas"}, READ)
    assert [p["name"] for p in saved["saved"]] == ["Brujas"]


async def test_two_stays_cannot_share_a_night(api) -> None:
    trip = await flanders(api)
    ghent = trip["stays"][1]

    answer = await content(
        api, "update_stay", {"stay_id": ghent["stay_id"], "arrives_on": "2025-03-08"}
    )

    assert answer["code"] == "STAY_OVERLAP"
    assert [c["name"] for c in answer["conflicts"]] == ["Brujas"]


async def test_leaving_one_and_arriving_at_another_the_same_day_is_fine(api) -> None:
    trip = await flanders(api)
    bruges = trip["stays"][0]

    moved = await content(
        api, "update_stay", {"stay_id": bruges["stay_id"], "arrives_on": "2025-03-08"}
    )

    assert moved["trip"]["stays"][0]["nights"] == 1
    assert moved["trip"]["stays"][0]["leaves_on"] == moved["trip"]["stays"][1]["arrives_on"]


async def test_a_new_stay_that_overlaps_is_refused_in_the_app_too(api) -> None:
    trip = await flanders(api)
    lille = (await api.post("/places", json=LILLE)).json()

    refused = await api.post(
        f"/trips/{trip['trip_id']}/stays",
        json={"place_id": lille["id"], "arrives_on": "2025-03-08", "leaves_on": "2025-03-10"},
    )

    assert refused.status_code == 409
    assert "no comparten noche" in refused.json()["detail"]


async def test_a_stay_outside_the_trip_is_out_of_range(api) -> None:
    trip = await flanders(api)

    answer = await content(
        api, "update_stay", {"stay_id": trip["stays"][1]["stay_id"], "leaves_on": "2025-03-12"}
    )

    assert answer["code"] == "DATE_OUT_OF_RANGE"
    assert answer["conflicts"][0]["date"] == "2025-03-12"


async def test_another_place_for_a_stay_takes_its_legs_and_redoes_the_km(api) -> None:
    trip = await flanders(api)
    plane_before = trip["legs"][0]["km"]

    moved = await content(
        api, "update_stay", {"stay_id": trip["stays"][0]["stay_id"], "place": LILLE}
    )

    plane, train = moved["trip"]["legs"]
    assert (plane["to"], train["from"]) == ("Lille", "Lille")
    assert plane["to_stay_id"] == moved["trip"]["stays"][0]["stay_id"]
    assert plane["km"] < plane_before
    assert moved["trip"]["km"] == round(plane["km"] + train["km"], 1)


async def test_a_stay_with_pieces_hanging_is_not_removed_and_says_which(api) -> None:
    trip = await flanders(api)

    answer = await content(api, "remove_stay", {"stay_id": trip["stays"][0]["stay_id"]})

    assert answer["code"] == "HAS_DEPENDENTS"
    assert {(c["kind"], c["name"]) for c in answer["conflicts"]} == {
        ("visit", "Damme"),
        ("leg", "Madrid → Brujas"),
        ("leg", "Brujas → Gante"),
    }
    assert len((await content(api, "get_trip", {"trip_id": trip["trip_id"]}, READ))["stays"]) == 2


async def test_detaching_keeps_the_visits_and_the_legs(api) -> None:
    trip = await flanders(api)

    answer = await content(
        api, "remove_stay", {"stay_id": trip["stays"][0]["stay_id"], "on_dependents": "detach"}
    )

    after = answer["trip"]
    assert answer["detached_dependents"] == {"visits": 1, "legs": 2}
    assert [s["name"] for s in after["stays"]] == ["Gante"]
    assert [(v["name"], v["stay_id"]) for v in after["visits"]] == [("Damme", None)]
    assert [(leg["from"], leg["from_stay_id"]) for leg in after["legs"]] == [
        ("Madrid", None),
        ("Brujas", None),
    ]


async def test_deleting_a_stay_with_its_pieces_rehearsed_and_for_real(api) -> None:
    trip = await flanders(api)
    stay_id = trip["stays"][0]["stay_id"]

    rehearsed = await content(
        api, "remove_stay", {"stay_id": stay_id, "on_dependents": "delete", "dry_run": True}
    )
    unchanged = await content(api, "get_trip", {"trip_id": trip["trip_id"]}, READ)
    done = await content(api, "remove_stay", {"stay_id": stay_id, "on_dependents": "delete"})

    assert rehearsed["dry_run"] is True
    assert rehearsed["deleted_dependents"] == {"visits": 1, "legs": 2}
    assert (len(unchanged["stays"]), len(unchanged["legs"])) == (2, 2)
    after = done["trip"]
    assert ([s["name"] for s in after["stays"]], after["visits"], after["legs"]) == (
        ["Gante"],
        [],
        [],
    )
    assert after["km"] == 0
    regions = await content(api, "get_travel", {"level": "region"}, READ)
    assert [a["places"] for a in regions["areas"]] == [["Gante"]]


async def test_a_visit_on_another_day_moves_to_the_stay_of_that_day(api) -> None:
    trip = await flanders(api)
    [visit] = trip["visits"]

    moved = await content(
        api, "update_visit", {"visit_id": visit["visit_id"], "visited_on": "2025-03-10"}
    )
    loose = await content(api, "update_visit", {"visit_id": visit["visit_id"], "stay_id": None})

    assert moved["trip"]["visits"][0]["stay_id"] == trip["stays"][1]["stay_id"]
    assert loose["trip"]["visits"][0]["stay_id"] is None
    assert loose["trip"]["visits"][0]["visited_on"] == "2025-03-10"


async def test_a_visit_outside_the_trip_is_out_of_range(api) -> None:
    trip = await flanders(api)

    answer = await content(
        api, "update_visit", {"visit_id": trip["visits"][0]["visit_id"], "visited_on": "2025-04-01"}
    )

    assert answer["code"] == "DATE_OUT_OF_RANGE"


async def test_removing_a_visit_takes_its_region_off_the_map(api) -> None:
    trip = await content(
        api, "create_trip", {"title": "Lille", "starts_on": "2025-05-01", "ends_on": "2025-05-02"}
    )
    trip_id = trip["trip"]["trip_id"]
    await content(
        api,
        "add_stay",
        {"trip_id": trip_id, "place": LILLE, "arrives_on": "2025-05-01", "leaves_on": "2025-05-02"},
    )
    added = await content(
        api, "add_visit", {"trip_id": trip_id, "place": BRUGES, "visited_on": "2025-05-02"}
    )

    await content(api, "remove_visit", {"visit_id": added["trip"]["visits"][0]["visit_id"]})

    visited = await content(api, "get_travel", {}, READ)
    assert [a["code"] for a in visited["areas"]] == ["FR"]


async def test_another_mode_or_end_redoes_the_km(api) -> None:
    trip = await flanders(api)
    train = trip["legs"][1]

    by_car = await content(api, "update_leg", {"leg_id": train["leg_id"], "mode": "car"})
    to_lille = await content(api, "update_leg", {"leg_id": train["leg_id"], "to_place": LILLE})

    car = by_car["trip"]["legs"][1]
    assert car["mode"] == "car"
    assert car["km"] == round(train["km"] / 1.2 * 1.25, 1)
    lille = to_lille["trip"]["legs"][1]
    assert (lille["to"], lille["to_stay_id"], lille["mode"]) == ("Lille", None, "car")
    assert lille["km"] != car["km"]


async def test_whether_a_leg_is_drawn_survives_other_corrections(api) -> None:
    trip = await flanders(api)
    train = trip["legs"][1]

    hidden = await content(api, "update_leg", {"leg_id": train["leg_id"], "on_map": False})
    by_car = await content(api, "update_leg", {"leg_id": train["leg_id"], "mode": "car"})
    again = await content(api, "update_leg", {"leg_id": train["leg_id"], "on_map": None})

    assert train["on_map"] is None
    assert hidden["trip"]["legs"][1]["on_map"] is False
    car = by_car["trip"]["legs"][1]
    assert (car["mode"], car["on_map"]) == ("car", False)
    assert again["trip"]["legs"][1]["on_map"] is None


async def test_a_leg_from_and_to_the_same_place_is_refused(api) -> None:
    trip = await flanders(api)
    train = trip["legs"][1]

    answer = await content(
        api, "update_leg", {"leg_id": train["leg_id"], "to_stay_id": trip["stays"][0]["stay_id"]}
    )

    assert answer["code"] == "INVALID"


async def test_removing_a_leg_takes_its_km(api) -> None:
    trip = await flanders(api)
    plane, train = trip["legs"]

    answer = await content(api, "remove_leg", {"leg_id": plane["leg_id"]})

    assert answer["trip"]["km"] == train["km"]


async def test_correcting_and_removing_an_expense_redoes_the_cost_per_day(api) -> None:
    trip = await flanders(api)
    [expense] = trip["expenses"]

    corrected = await content(
        api,
        "update_expense",
        {"expense_id": expense["expense_id"], "amount_eur_per_person": "150", "note": "con cena"},
    )
    removed = await content(api, "remove_expense", {"expense_id": expense["expense_id"]})

    after = corrected["trip"]["expenses"][0]
    assert (after["concept"], after["amount_eur_per_person"], after["note"]) == (
        "Hotel",
        150.0,
        "con cena",
    )
    assert corrected["trip"]["spend"]["per_day_eur"] == 30.0
    assert (removed["trip"]["expenses"], removed["trip"]["spend"]["per_day_eur"]) == ([], None)


async def test_a_piece_that_does_not_exist_is_not_found(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    for name, key in (
        ("remove_visit", "visit_id"),
        ("remove_leg", "leg_id"),
        ("remove_expense", "expense_id"),
        ("remove_stay", "stay_id"),
        ("remove_other_place", "other_place_id"),
    ):
        assert (await content(api, name, {key: missing}))["code"] == "NOT_FOUND", name


async def test_an_other_place_is_corrected_and_removed(api) -> None:
    added = await content(api, "add_other_place", {"place": LILLE, "note": "de paso"})
    other_id = added["other_place_id"]

    moved = await content(
        api, "update_other_place", {"other_place_id": other_id, "place": SEVILLE, "note": None}
    )
    removed = await content(api, "remove_other_place", {"other_place_id": other_id})

    assert (moved["name"], moved["country"], moved["note"]) == ("Sevilla", "ES", None)
    assert removed["removed"]["other_place_id"] == other_id
    assert (await content(api, "get_travel", {}, READ))["areas"] == []


async def test_two_other_places_cannot_be_the_same_place(api) -> None:
    lille = await content(api, "add_other_place", {"place": LILLE})
    seville = await content(api, "add_other_place", {"place": SEVILLE})

    answer = await content(
        api,
        "update_other_place",
        {"other_place_id": seville["other_place_id"], "place": {"place_id": lille["place_id"]}},
    )

    assert answer["code"] == "DUPLICATE_PLACE"


async def test_renaming_a_place_changes_it_in_every_trip_and_says_which(api) -> None:
    trip = await flanders(api)
    other = await content(
        api, "create_trip", {"title": "Brujas", "starts_on": "2025-06-01", "ends_on": "2025-06-02"}
    )
    place_id = trip["stays"][0]["place_id"]
    await content(
        api,
        "add_visit",
        {"trip_id": other["trip"]["trip_id"], "place": {"place_id": place_id}},
    )

    renamed = await content(api, "update_place", {"place_id": place_id, "name": "Brugge"})

    assert renamed["place"]["name"] == "Brugge"
    assert {t["title"] for t in renamed["affected_trips"]} == {"Flandes", "Brujas"}
    again = await content(api, "get_trip", {"trip_id": trip["trip_id"]}, READ)
    assert again["stays"][0]["name"] == "Brugge"
    assert again["legs"][1]["from"] == "Brugge"


async def test_resolving_a_place_again_redoes_its_country_and_km(api) -> None:
    trip = await flanders(api)
    stay = trip["stays"][0]
    wrong = await content(
        api,
        "update_place",
        {"place_id": stay["place_id"], "candidate": {**LILLE, "name": "Brujas"}},
    )
    assert wrong["place"]["country"] == "FR"

    rehearsed = await content(
        api,
        "update_place",
        {"place_id": stay["place_id"], "candidate": BRUGES, "dry_run": True},
    )
    still = await content(api, "get_trip", {"trip_id": trip["trip_id"]}, READ)
    fixed = await content(api, "update_place", {"place_id": stay["place_id"], "candidate": BRUGES})

    assert rehearsed["dry_run"] is True
    assert [t["title"] for t in rehearsed["affected_trips"]] == ["Flandes"]
    assert rehearsed["place"]["country"] == "BE"
    assert still["stays"][0]["country"] == "FR"
    assert fixed["place"]["region"] == "BE-VLG"
    after = await content(api, "get_trip", {"trip_id": trip["trip_id"]}, READ)
    assert after["legs"][0]["km"] == trip["legs"][0]["km"]
    assert after["countries"] == ["BE"]


async def test_a_place_resolved_to_one_already_saved_is_a_duplicate(api) -> None:
    trip = await flanders(api)
    bruges = {**BRUGES, "osm_type": "relation", "osm_id": 1}
    ghent = {**GHENT, "osm_type": "relation", "osm_id": 2}
    saved = await content(
        api, "update_place", {"place_id": trip["stays"][0]["place_id"], "candidate": bruges}
    )
    assert saved["place"]["name"] == "Brujas"
    await content(
        api, "update_place", {"place_id": trip["stays"][1]["place_id"], "candidate": ghent}
    )

    answer = await content(
        api, "update_place", {"place_id": trip["stays"][1]["place_id"], "candidate": bruges}
    )

    assert answer["code"] == "DUPLICATE_PLACE"
    assert answer["conflicts"] == [{"place_id": trip["stays"][0]["place_id"]}]


async def test_correcting_and_deleting_with_only_the_read_scope_is_refused_by_postgres(api) -> None:
    trip = await flanders(api)

    for name, arguments in (
        ("update_trip", {"trip_id": trip["trip_id"], "title": "X"}),
        ("delete_trip", {"trip_id": trip["trip_id"], "title": "Flandes"}),
        ("remove_leg", {"leg_id": trip["legs"][0]["leg_id"]}),
    ):
        response = await call(api, name, arguments, headers=READ)
        assert response.status_code == 403, name
    assert (await call(api, "get_trips", {}, headers=WRITE)).status_code == 200
