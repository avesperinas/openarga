from __future__ import annotations

from sqlalchemy import text
from travel_kit import make_trip

WRITE = {"x-arga-scopes": "travel:read travel:write"}


async def tool(api, name: str, body: dict) -> dict:
    response = await api.post(f"/tools/{name}", json=body, headers=WRITE)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_yen_paid_by_me_is_in_euros_and_per_person(api, hub) -> None:
    trip = await make_trip(
        api, "Japón", "2027-04-01", "2027-04-05", travellers=2, companions=["Luis"]
    )

    told = await tool(
        api,
        "record_trip_expense",
        {
            "trip_id": trip["id"],
            "category": "lodging",
            "concept": "Ryokan",
            "amount": "12000",
            "currency": "jpy",
            "paid_by": "yo",
            "spent_on": "2027-04-03",
        },
    )
    read = await tool(api, "get_trip", {"trip_id": trip["id"]})

    [expense] = read["expenses"]
    assert told["recorded"] is True
    assert expense["amount_eur_per_person"] == 33.9
    assert expense["paid"] | {"paid_by": None} == {
        "amount": 12000.0,
        "currency": "JPY",
        "total_eur": 67.8,
        "fx_rate": 0.00565,
        "fx_on": "2027-04-02",
        "spent_on": "2027-04-03",
        "paid_by": None,
    }
    people = {one["name"]: one for one in read["people"]}
    assert set(people) == {"Yo", "Luis"} and people["Yo"]["me"] is True
    assert expense["paid"]["paid_by"] == "Yo"


async def test_a_currency_the_ecb_does_not_publish_needs_its_rate(api, hub) -> None:
    trip = await make_trip(api, "Vietnam", "2027-02-01", "2027-02-10")

    refused = await api.post(
        "/tools/record_trip_expense",
        json={
            "trip_id": trip["id"],
            "category": "other",
            "concept": "Pho",
            "amount": "100000",
            "currency": "VND",
        },
        headers=WRITE,
    )
    kept = await tool(
        api,
        "record_trip_expense",
        {
            "trip_id": trip["id"],
            "category": "other",
            "concept": "Pho",
            "amount": "100000",
            "currency": "VND",
            "fx_rate": "0.000036",
        },
    )

    assert refused.json()["content"]["code"] == "FX_UNKNOWN"
    assert kept["trip"]["expenses"][0]["amount_eur_per_person"] == 3.6


async def test_old_expenses_read_as_euros_and_an_old_code_edit_wins(api, hub, schema) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12", travellers=2)
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "lodging", "concept": "Hotel", "amount_eur": "100"},
    )
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "other", "concept": "Cena", "amount": "50", "currency": "EUR"},
    )
    async with schema.begin() as connection:
        await connection.execute(
            text("update travel.travel_expense set amount_eur = 40 where concept = 'Cena'")
        )

    expenses = {e["concept"]: e for e in (await api.get(f"/trips/{trip['id']}")).json()["expenses"]}

    assert (expenses["Hotel"]["currency"], expenses["Hotel"]["total_eur"]) == ("EUR", 200.0)
    assert (expenses["Cena"]["amount_eur"], expenses["Cena"]["total_eur"]) == (40.0, 80.0)


async def test_with_more_travellers_the_total_stays_and_each_pays_less(api, hub) -> None:
    trip = await make_trip(api, "Lisboa", "2027-03-10", "2027-03-12", travellers=2)
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "other", "concept": "Cena", "amount": "90", "currency": "EUR"},
    )

    more = await tool(api, "update_trip", {"trip_id": trip["id"], "travellers": 3})

    [expense] = more["trip"]["expenses"]
    assert (expense["amount_eur_per_person"], expense["paid"]["total_eur"]) == (30.0, 90.0)
