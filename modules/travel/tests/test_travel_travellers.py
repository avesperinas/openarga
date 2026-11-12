from __future__ import annotations

from travel_kit import make_trip

WRITE = {"x-arga-scopes": "travel:read travel:write"}


async def test_a_renamed_companion_is_not_created_again(api) -> None:
    trip = await make_trip(
        api, "Roma", "2027-05-10", "2027-05-12", travellers=3, companions=["Luis"]
    )
    before = {
        one["name"]: one["id"] for one in (await api.get(f"/trips/{trip['id']}/travellers")).json()
    }

    renamed = await api.patch(
        f"/trips/{trip['id']}/travellers/{before['Luis']}", json={"name": "Luis G."}
    )
    taken = await api.patch(
        f"/trips/{trip['id']}/travellers/{before['Viajero 3']}", json={"name": "luis g."}
    )
    again = (await api.get(f"/trips/{trip['id']}/travellers")).json()

    assert renamed.status_code == 200, renamed.text
    assert taken.status_code == 409
    assert [one["name"] for one in again] == ["Yo", "Luis G.", "Viajero 3"]
    assert (await api.get(f"/trips/{trip['id']}")).json()["companions"] == ["Luis G."]


async def test_list_items_go_to_someone_and_claude_says_whose(api) -> None:
    trip = await make_trip(
        api, "Roma", "2027-05-10", "2027-05-12", travellers=2, companions=["Eva"]
    )
    await api.post(
        "/tools/update_traveller",
        json={"trip_id": trip["id"], "traveller": "Eva", "name": "Eva M."},
        headers=WRITE,
    )
    added = await api.post(
        "/tools/add_check_items",
        json={
            "trip_id": trip["id"],
            "items": ["Entradas del Coliseo"],
            "list": "todo",
            "for_traveller": "Eva M.",
        },
        headers=WRITE,
    )
    [item] = (await api.get(f"/trips/{trip['id']}/checklist")).json()
    cleared = await api.patch(
        f"/trips/{trip['id']}/checklist/{item['id']}", json={"traveller_id": None}
    )

    assert added.json()["content"]["todo"][0]["for"] == "Eva M."
    assert item["traveller_id"] is not None
    assert cleared.json()[0]["traveller_id"] is None
