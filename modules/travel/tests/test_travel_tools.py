from __future__ import annotations

from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"
READ = {"x-arga-scopes": "travel:read"}
WRITE = {"x-arga-scopes": "travel:read travel:write"}

BRUGES = {
    "osm_type": "relation",
    "osm_id": 562654,
    "lat": "51.2085526",
    "lon": "3.2267720",
    "addresstype": "city",
    "name": "Brujas",
    "display_name": "Brujas, Flandes Occidental, Flandes, Bélgica",
    "address": {"ISO3166-2-lvl4": "BE-VLG", "country_code": "be"},
}
HOME = {
    "osm_type": "relation",
    "osm_id": 5326784,
    "lat": "40.4167",
    "lon": "-3.7033",
    "addresstype": "city",
    "name": "Madrid",
    "display_name": "Madrid, Comunidad de Madrid, España",
    "address": {"ISO3166-2-lvl4": "ES-MD", "country_code": "es"},
}


def call(api, name: str, arguments: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


async def content(api, name: str, arguments: dict, headers: dict = WRITE) -> dict:
    response = await call(api, name, arguments, headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_the_listed_tools_are_the_ones_the_manifest_declares(api) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())
    served = (await api.get("/tools")).json()

    assert {tool["name"] for tool in served} == {tool["name"] for tool in manifest["tools"]}
    assert all("properties" in tool["input_schema"] for tool in served)


def test_only_the_verbs_write_and_the_only_wide_deletes_can_be_rehearsed() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text())

    writing = {t["name"] for t in manifest["tools"] if t["scope"] == "travel:write"}
    verbs = {name.split("_")[0] for name in writing}

    assert verbs == {
        "check",
        "copy",
        "create",
        "update",
        "archive",
        "unarchive",
        "delete",
        "add",
        "remove",
        "record",
        "share",
        "confirm",
        "unconfirm",
        "move",
        "plan",
        "write",
    }
    assert {"delete_trip", "remove_stay"} <= writing
    from travel.tools import TOOLS

    for wide in ("delete_trip", "remove_stay", "update_trip", "update_stay", "update_place"):
        assert "dry_run" in TOOLS[wide].arguments.model_fields, wide


async def test_without_a_scope_of_this_module_nothing_runs(api) -> None:
    assert (await call(api, "get_trips", {}, headers={})).status_code == 403


async def test_writing_with_only_the_read_scope_is_refused_by_postgres(api) -> None:
    response = await call(
        api,
        "create_trip",
        {"title": "Roma", "starts_on": "2025-01-01", "ends_on": "2025-01-03"},
        headers=READ,
    )

    assert response.status_code == 403
    assert "mod_travel_read" in response.json()["detail"]


async def test_a_trip_told_in_words_ends_up_resolved_and_on_the_map(api, hub) -> None:
    hub.places = [BRUGES]
    found = await content(api, "find_place", {"query": "Brujas"}, READ)
    [bruges] = found["candidates"]
    assert (bruges["country_code"], bruges["region_code"]) == ("BE", "BE-VLG")
    assert bruges["region"] == "Flandes"

    created = await content(
        api,
        "create_trip",
        {"title": "Brujas", "starts_on": "2025-03-07", "ends_on": "2025-03-09", "travellers": 2},
    )
    trip_id = created["trip"]["trip_id"]
    stayed = await content(
        api,
        "add_stay",
        {
            "trip_id": trip_id,
            "place": bruges,
            "arrives_on": "2025-03-07",
            "leaves_on": "2025-03-09",
            "accommodation": "Hotel",
        },
    )
    hub.places = [HOME]
    [home] = (await content(api, "find_place", {"query": "Madrid"}, READ))["candidates"]
    flown = await content(
        api,
        "add_leg",
        {
            "trip_id": trip_id,
            "mode": "plane",
            "from_place": home,
            "to_stay_id": stayed["trip"]["stays"][0]["stay_id"],
            "travelled_on": "2025-03-07",
        },
    )
    spent = await content(
        api,
        "record_trip_expense",
        {
            "trip_id": trip_id,
            "category": "transport",
            "concept": "Vuelos",
            "amount_eur_per_person": "90",
        },
    )

    assert flown["trip"]["legs"][0]["mode"] == "plane"
    assert 1300 < flown["trip"]["legs"][0]["km"] < 1400
    assert spent["spend"]["per_day_eur"] == 30.0
    atlas = (await api.get("/atlas")).json()
    [stay] = atlas["trips"][0]["stays"]
    assert (stay["place"]["country_code"], stay["place"]["region_code"]) == ("BE", "BE-VLG")
    visited = await content(api, "get_travel", {"level": "region"}, READ)
    assert [area["code"] for area in visited["areas"]] == ["BE-VLG"]
    assert "ES" not in [a["code"] for a in (await content(api, "get_travel", {}, READ))["areas"]]


async def test_a_place_already_saved_is_offered_first(api, hub) -> None:
    hub.places = [BRUGES]
    [bruges] = (await content(api, "find_place", {"query": "Brujas"}, READ))["candidates"]
    trip = await content(
        api, "create_trip", {"title": "Flandes", "starts_on": "2025-03-07", "ends_on": "2025-03-09"}
    )
    await content(
        api,
        "add_stay",
        {
            "trip_id": trip["trip"]["trip_id"],
            "place": bruges,
            "arrives_on": "2025-03-07",
            "leaves_on": "2025-03-09",
        },
    )

    again = await content(api, "find_place", {"query": "Brujas"}, READ)

    assert [(p["name"], p["country"]) for p in again["saved"]] == [("Brujas", "BE")]


async def test_with_nominatim_down_it_says_so_and_the_place_can_be_kept_unresolved(api, hub):
    hub.down = True

    found = await content(api, "find_place", {"query": "Brujas"}, READ)
    trip = await content(
        api, "create_trip", {"title": "Flandes", "starts_on": "2025-03-07", "ends_on": "2025-03-09"}
    )
    stayed = await content(
        api,
        "add_stay",
        {
            "trip_id": trip["trip"]["trip_id"],
            "place": {"name": "Brujas", "country_code": "BE"},
            "arrives_on": "2025-03-07",
            "leaves_on": "2025-03-09",
        },
    )

    assert found["candidates"] == []
    assert found["failed"][0]["source"] == "nominatim"
    [stay] = stayed["trip"]["stays"]
    assert (stay["country"], stay["region"], stay["resolved"]) == ("BE", None, False)


async def test_the_same_trip_loaded_twice_is_one_trip(api) -> None:
    trip = {"title": "Oporto", "starts_on": "2023-05-01", "ends_on": "2023-05-04"}

    first = await content(api, "create_trip", trip)
    second = await content(api, "create_trip", {**trip, "title": "oporto"})

    assert (first["created"], second["created"]) == (True, False)
    assert second["trip"]["trip_id"] == first["trip"]["trip_id"]
    assert (await content(api, "get_trips", {}, READ))["total"] == 1


async def test_a_stay_outside_the_trip_is_said_and_nothing_is_saved(api) -> None:
    trip = await content(
        api, "create_trip", {"title": "Oporto", "starts_on": "2023-05-01", "ends_on": "2023-05-04"}
    )

    answer = await content(
        api,
        "add_stay",
        {
            "trip_id": trip["trip"]["trip_id"],
            "place": {"name": "Oporto", "lat": 41.15, "lon": -8.61},
            "arrives_on": "2023-04-30",
            "leaves_on": "2023-05-04",
        },
    )

    assert "fuera del viaje" in answer["error"]
    detail = await content(api, "get_trip", {"title": "opor"}, READ)
    assert detail["stays"] == []


async def test_a_visit_hangs_from_the_stay_of_its_day(api) -> None:
    trip = await content(
        api, "create_trip", {"title": "Flandes", "starts_on": "2025-03-07", "ends_on": "2025-03-10"}
    )
    trip_id = trip["trip"]["trip_id"]
    stayed = await content(
        api,
        "add_stay",
        {
            "trip_id": trip_id,
            "place": {"name": "Brujas", "lat": 51.2085, "lon": 3.2267},
            "arrives_on": "2025-03-07",
            "leaves_on": "2025-03-10",
        },
    )

    visited = await content(
        api,
        "add_visit",
        {
            "trip_id": trip_id,
            "place": {"name": "Gante", "lat": 51.0543, "lon": 3.7174},
            "visited_on": "2025-03-08",
        },
    )

    [visit] = visited["trip"]["visits"]
    assert visit["stay_id"] == stayed["trip"]["stays"][0]["stay_id"]
    assert visit["region"] == "BE-VLG"


async def test_the_summary_groups_by_year_country_and_mode(api) -> None:
    trip = await content(
        api, "create_trip", {"title": "Flandes", "starts_on": "2025-03-07", "ends_on": "2025-03-09"}
    )
    trip_id = trip["trip"]["trip_id"]
    await content(
        api,
        "add_stay",
        {
            "trip_id": trip_id,
            "place": {"name": "Brujas", "lat": 51.2085, "lon": 3.2267},
            "arrives_on": "2025-03-07",
            "leaves_on": "2025-03-09",
        },
    )
    await content(
        api,
        "record_trip_expense",
        {
            "trip_id": trip_id,
            "category": "lodging",
            "concept": "Hotel",
            "amount_eur_per_person": 150,
        },
    )

    by_year = await content(api, "get_travel", {"view": "summary", "group_by": "year"}, READ)
    by_country = await content(api, "get_travel", {"view": "summary", "group_by": "country"}, READ)

    assert by_year["totals"]["europe_visited"] == "1 de 44"
    assert by_year["groups"][0]["year"] == 2025
    assert by_country["groups"][0]["spend_per_night_eur"] == 75.0


async def test_an_old_trip_without_dates_is_told_as_an_other_place(api, hub) -> None:
    hub.places = [BRUGES]
    [bruges] = (await content(api, "find_place", {"query": "Brujas"}, READ))["candidates"]

    added = await content(api, "add_other_place", {"place": bruges, "note": "de niño"})
    again = await content(api, "add_other_place", {"place": {"place_id": added["place_id"]}})

    assert (added["country"], added["region"], added["note"]) == ("BE", "BE-VLG", "de niño")
    assert again["other_place_id"] == added["other_place_id"]
    visited = await content(api, "get_travel", {}, READ)
    assert [(a["code"], a["trips"], a["first_visit"], a["places"]) for a in visited["areas"]] == [
        ("BE", 0, None, ["Brujas"])
    ]
    since = await content(api, "get_travel", {"since": "2020-01-01"}, READ)
    assert since["areas"] == []
    summary = await content(api, "get_travel", {"view": "summary", "group_by": "country"}, READ)
    assert (summary["totals"]["trips"], summary["totals"]["countries"]) == (0, 1)


async def test_an_other_place_that_does_not_exist_is_said(api) -> None:
    missing = {"place_id": "00000000-0000-4000-8000-000000000000"}

    answer = await content(api, "add_other_place", {"place": missing})

    assert "no existe" in answer["error"]


async def test_an_other_place_with_only_the_read_scope_is_refused_by_postgres(api) -> None:
    response = await call(api, "add_other_place", {"place": {"name": "Lyon"}}, headers=READ)

    assert response.status_code == 403


async def test_a_trip_is_read_once_with_what_is_asked_of_it(api) -> None:
    made = await content(
        api, "create_trip", {"title": "Flandes", "starts_on": "2025-03-07", "ends_on": "2025-03-09"}
    )
    trip_id = made["trip"]["trip_id"]
    every = ["itinerary", "bookings", "balance", "notes", "checklist", "documents"]

    bare = await content(api, "get_trip", {"trip_id": trip_id}, READ)
    whole = await content(api, "get_trip", {"trip_id": trip_id, "include": every}, READ)
    wrong = await call(api, "get_trip", {"trip_id": trip_id, "include": ["fotos"]}, READ)

    parts = {"itinerary", "bookings", "balance", "trip_notes", "checklist", "documents"}
    assert not parts & set(bare)
    assert parts <= set(whole)
    assert whole["trip_notes"] == [] and whole["documents"] == []
    assert whole["notes"] == bare["notes"]
    assert set(whole["checklist"]) == {"packing", "todo"}
    assert "days" in whole["itinerary"]
    assert wrong.status_code == 422


async def test_what_was_lived_is_one_read_with_two_views(api) -> None:
    places = await content(api, "get_travel", {}, READ)
    summary = await content(api, "get_travel", {"view": "summary", "group_by": "mode"}, READ)

    assert set(places) >= {"level", "total", "areas", "other_places"}
    assert summary["group_by"] == "mode" and "totals" in summary
