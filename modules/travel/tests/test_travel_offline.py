from __future__ import annotations

from uuid import uuid4

from travel_kit import make_trip


async def test_an_expense_sent_twice_with_its_id_is_one(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    body = {"id": str(uuid4()), "category": "other", "concept": "Café", "amount_eur": "3.50"}

    first = await api.post(f"/trips/{trip['id']}/expenses", json=body)
    again = await api.post(f"/trips/{trip['id']}/expenses", json=body)

    assert (first.status_code, again.status_code) == (201, 201)
    assert [e["id"] for e in again.json()["expenses"]] == [body["id"]]


async def test_it_says_who_is_looking(api, person) -> None:
    assert (await api.get("/me")).json() == {"user_id": str(person)}
