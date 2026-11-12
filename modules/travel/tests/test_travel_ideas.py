from __future__ import annotations

from travel_kit import BRUGES, GHENT, make_trip, place, stay

WRITE = {"x-arga-scopes": "travel:read travel:write"}


async def an_idea(api) -> dict:
    created = await api.post(
        "/ideas",
        json={
            "title": "Flandes en primavera",
            "budget_eur": "900",
            "days_min": 4,
            "days_max": 6,
            "months": [5, 4, 4],
            "tags": ["cerveza"],
        },
    )
    assert created.status_code == 201, created.text
    idea = created.json()
    for candidate in (BRUGES, GHENT):
        found = await place(api, candidate)
        response = await api.post(f"/ideas/{idea['id']}/places", json={"place_id": found["id"]})
        assert response.status_code == 201, response.text
    return response.json()


async def test_an_idea_has_its_places_months_and_budget_and_counts_for_nothing(api) -> None:
    idea = await an_idea(api)

    assert (idea["months"], idea["budget_eur"], idea["days_min"], idea["days_max"]) == (
        [4, 5],
        900.0,
        4,
        6,
    )
    assert [one["place"]["name"] for one in idea["places"]] == ["Brujas", "Gante"]
    assert idea["countries"] == ["BE"]
    assert (await api.get("/stats")).json()["countries"] == 0
    wrong = await api.post("/ideas", json={"title": "Mal", "days_min": 6, "days_max": 2})
    assert wrong.status_code == 422


async def test_an_idea_becomes_a_plan_with_its_places_waiting(api) -> None:
    idea = await an_idea(api)

    planned = await api.post(
        f"/ideas/{idea['id']}/plan",
        json={"starts_on": "2027-05-01", "ends_on": "2027-05-05", "travellers": 2},
    )
    trip = planned.json()
    days = (await api.get(f"/trips/{trip['id']}/days")).json()
    after = (await api.get(f"/ideas/{idea['id']}")).json()

    assert planned.status_code == 201, planned.text
    assert (trip["status"], trip["idea_id"], trip["tags"]) == ("plan", idea["id"], ["cerveza"])
    assert [b["title"] for b in days["unscheduled"]] == ["Brujas", "Gante"]
    assert [(t["title"], t["phase"]) for t in after["trips"]] == [("Flandes en primavera", "plan")]


async def test_deleting_an_idea_keeps_its_trips(api) -> None:
    idea = await an_idea(api)
    planned = await api.post(
        f"/ideas/{idea['id']}/plan", json={"starts_on": "2027-05-01", "ends_on": "2027-05-03"}
    )

    gone = await api.delete(f"/ideas/{idea['id']}")
    trip = (await api.get(f"/trips/{planned.json()['id']}")).json()

    assert gone.status_code == 204
    assert (trip["title"], trip["idea_id"]) == ("Flandes en primavera", None)


async def test_claude_notes_an_idea_and_plans_it(api) -> None:
    created = await api.post(
        "/tools/create_idea",
        json={
            "title": "Japón en otoño",
            "destinations": [BRUGES],
            "months": [11],
            "days_min": 12,
            "days_max": 15,
            "budget_eur_per_person": "3000",
        },
        headers=WRITE,
    )
    idea = created.json()["content"]["idea"]
    planned = await api.post(
        "/tools/plan_idea",
        json={"idea_id": idea["idea_id"], "starts_on": "2027-11-01", "ends_on": "2027-11-14"},
        headers=WRITE,
    )
    rehearsed = await api.post(
        "/tools/delete_idea",
        json={"idea_id": idea["idea_id"], "title": "Japón en otoño", "dry_run": True},
        headers=WRITE,
    )
    listed = await api.post("/tools/get_ideas", json={}, headers=WRITE)

    assert created.status_code == 200, created.text
    assert (idea["months"], idea["days"]) == (["noviembre"], {"min": 12, "max": 15})
    assert planned.json()["content"]["trip"]["phase"] == "plan"
    assert rehearsed.json()["content"]["dry_run"] is True
    assert listed.json()["content"]["ideas"][0]["trips"][0]["phase"] == "plan"


async def test_a_trip_that_was_done_is_not_touched_by_an_idea(api) -> None:
    done = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    await stay(api, done["id"], BRUGES, "2025-04-10", "2025-04-12")
    await an_idea(api)

    assert (await api.get("/stats")).json()["countries"] == 1
