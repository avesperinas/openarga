from __future__ import annotations

from travel_kit import make_trip

WRITE = {"x-arga-scopes": "travel:read travel:write"}


async def test_a_plan_from_an_idea_inherits_its_budget_and_says_what_is_left(api) -> None:
    idea = (await api.post("/ideas", json={"title": "Japón", "budget_eur": "3000"})).json()
    trip = (
        await api.post(
            f"/ideas/{idea['id']}/plan", json={"starts_on": "2027-11-01", "ends_on": "2027-11-14"}
        )
    ).json()
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "transport", "concept": "Vuelos", "amount_eur": "1100"},
    )

    told = await api.post("/tools/get_trip", json={"trip_id": trip["id"]}, headers=WRITE)

    content = told.json()["content"]
    assert trip["budget_eur"] == 3000.0
    assert (content["budget_per_person_eur"], content["budget_left_per_person_eur"]) == (
        3000.0,
        1900.0,
    )


async def test_editing_without_the_budget_keeps_it_and_null_takes_it_away(api) -> None:
    trip = await make_trip(api, "Flandes", "2027-04-10", "2027-04-12", budget_eur="600")
    body = {"title": "Flandes", "starts_on": "2027-04-10", "ends_on": "2027-04-13"}

    kept = (await api.put(f"/trips/{trip['id']}", json=body)).json()
    cleared = await api.post(
        "/tools/update_trip",
        json={"trip_id": trip["id"], "budget_eur_per_person": None},
        headers=WRITE,
    )

    assert kept["budget_eur"] == 600.0
    assert cleared.json()["content"]["trip"]["budget_per_person_eur"] is None
