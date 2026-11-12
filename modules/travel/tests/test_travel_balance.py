from __future__ import annotations

from decimal import Decimal

from travel_kit import make_trip

from travel.money import minimal_transfers

WRITE = {"x-arga-scopes": "travel:read travel:write"}


def test_the_fewest_transfers_go_from_who_owes_most_to_who_is_owed_most() -> None:
    net = {"ana": Decimal("60"), "luis": Decimal("-20"), "eva": Decimal("-40")}

    assert minimal_transfers(net) == [
        ("eva", "ana", Decimal("40.00")),
        ("luis", "ana", Decimal("20.00")),
    ]
    assert minimal_transfers({"ana": Decimal(0), "luis": Decimal(0)}) == []


async def test_who_owes_whom_with_an_equal_and_a_custom_split_and_what_was_paid_back(api) -> None:
    trip = await make_trip(
        api, "Lisboa", "2027-03-10", "2027-03-12", travellers=3, companions=["Luis", "Eva"]
    )
    people = {
        one["name"]: one["id"] for one in (await api.get(f"/trips/{trip['id']}/travellers")).json()
    }
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={
            "category": "lodging",
            "concept": "Hotel",
            "amount": "90",
            "currency": "EUR",
            "paid_by": people["Yo"],
        },
    )
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={
            "category": "other",
            "concept": "Cena de Luis",
            "amount": "30",
            "currency": "EUR",
            "paid_by": people["Luis"],
            "shares": [{"traveller_id": people["Luis"], "amount": "30"}],
        },
    )
    await api.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "other", "concept": "Propinas", "amount_eur": "5"},
    )

    before = (await api.get(f"/trips/{trip['id']}/balance")).json()
    paid_back = await api.post(
        f"/trips/{trip['id']}/settlements",
        json={"from_traveller": people["Eva"], "to_traveller": people["Yo"], "amount_eur": "30"},
    )

    nets = {one["traveller"]["name"]: one["net_eur"] for one in before["people"]}
    assert nets == {"Yo": 60.0, "Luis": -30.0, "Eva": -30.0}
    assert [
        (t["from_traveller"]["name"], t["to_traveller"]["name"], t["amount_eur"])
        for t in before["transfers"]
    ] == [("Luis", "Yo", 30.0), ("Eva", "Yo", 30.0)]
    assert before["unassigned_eur"] == 15.0
    after = paid_back.json()
    assert {one["traveller"]["name"]: one["net_eur"] for one in after["people"]} == {
        "Yo": 30.0,
        "Luis": -30.0,
        "Eva": 0.0,
    }
    assert [s["amount_eur"] for s in after["settlements"]] == [30.0]


async def test_parts_that_do_not_add_up_are_refused(api) -> None:
    trip = await make_trip(
        api, "Roma", "2027-05-10", "2027-05-12", travellers=2, companions=["Luis"]
    )
    people = {
        one["name"]: one["id"] for one in (await api.get(f"/trips/{trip['id']}/travellers")).json()
    }

    refused = await api.post(
        f"/trips/{trip['id']}/expenses",
        json={
            "category": "other",
            "concept": "Cena",
            "amount": "50",
            "currency": "EUR",
            "paid_by": people["Yo"],
            "shares": [
                {"traveller_id": people["Yo"], "amount": "10"},
                {"traveller_id": people["Luis"], "amount": "10"},
            ],
        },
    )

    assert refused.status_code == 409
    assert (await api.get(f"/trips/{trip['id']}")).json()["expenses"] == []


async def test_claude_records_a_split_and_asks_the_balance(api) -> None:
    trip = await make_trip(
        api, "Roma", "2027-05-10", "2027-05-12", travellers=2, companions=["Luis"]
    )

    await api.post(
        "/tools/record_trip_expense",
        json={
            "trip_id": trip["id"],
            "category": "other",
            "concept": "Museos",
            "amount": "40",
            "currency": "EUR",
            "paid_by": "Luis",
            "shares": {"yo": "30", "Luis": "10"},
        },
        headers=WRITE,
    )
    told = await api.post(
        "/tools/get_trip", json={"trip_id": trip["id"], "include": ["balance"]}, headers=WRITE
    )
    content = told.json()["content"]["balance"]

    assert content["transfers"] == [{"from": "yo", "to": "Luis", "amount_eur": 30.0}]

    settled = await api.post(
        "/tools/record_settlement",
        json={
            "trip_id": trip["id"],
            "from_traveller": "yo",
            "to_traveller": "Luis",
            "amount_eur": "30",
        },
        headers=WRITE,
    )
    [paid] = settled.json()["content"]["balance"]["settlements"]
    undone = await api.post(
        "/tools/remove_settlement",
        json={"trip_id": trip["id"], "settlement_id": paid["settlement_id"]},
        headers=WRITE,
    )

    assert undone.status_code == 200, undone.text
    assert undone.json()["content"]["balance"]["settlements"] == []
    assert undone.json()["content"]["balance"]["transfers"] == content["transfers"]
