from __future__ import annotations

from uuid import uuid4

from travel_kit import make_trip

WRITE = {"x-arga-scopes": "travel:read travel:write"}


async def test_items_are_checked_unchecked_and_kept_in_order(api) -> None:
    trip = await make_trip(api, "Islandia", "2027-07-01", "2027-07-10", status="plan")
    same = str(uuid4())
    await api.post(
        f"/trips/{trip['id']}/checklist",
        json=[
            {"id": same, "text": "Chubasquero"},
            {"text": "Adaptador", "list": "packing"},
            {"text": "Reservar coche", "list": "todo"},
        ],
    )
    again = await api.post(
        f"/trips/{trip['id']}/checklist", json=[{"id": same, "text": "Chubasquero"}]
    )
    checked = await api.patch(f"/trips/{trip['id']}/checklist/{same}", json={"checked": True})
    unchecked = await api.patch(f"/trips/{trip['id']}/checklist/{same}", json={"checked": False})

    assert len(again.json()) == 3
    assert [(i["list"], i["text"], i["position"]) for i in again.json()] == [
        ("packing", "Chubasquero", 0),
        ("packing", "Adaptador", 1),
        ("todo", "Reservar coche", 0),
    ]
    assert next(i for i in checked.json() if i["id"] == same)["checked"] is True
    assert next(i for i in unchecked.json() if i["id"] == same)["checked"] is False


async def test_copying_another_trip_brings_its_lists_unchecked_and_without_repeats(api) -> None:
    before = await make_trip(api, "Noruega", "2026-07-01", "2026-07-10")
    added = await api.post(
        f"/trips/{before['id']}/checklist",
        json=[{"text": "Chubasquero"}, {"text": "Botas"}, {"text": "Seguro", "list": "todo"}],
    )
    await api.patch(
        f"/trips/{before['id']}/checklist/{added.json()[0]['id']}", json={"checked": True}
    )
    trip = await make_trip(api, "Islandia", "2027-07-01", "2027-07-10", status="plan")
    await api.post(f"/trips/{trip['id']}/checklist", json=[{"text": "chubasquero"}])

    copied = await api.post(
        f"/trips/{trip['id']}/checklist/copy",
        json={"from_trip_id": before["id"], "list": "packing"},
    )

    assert [(i["text"], i["checked"]) for i in copied.json()] == [
        ("chubasquero", False),
        ("Botas", False),
    ]


async def test_claude_adds_checks_and_reads_the_lists(api) -> None:
    trip = await make_trip(api, "Islandia", "2027-07-01", "2027-07-10", status="plan")
    added = await api.post(
        "/tools/add_check_items",
        json={"trip_id": trip["id"], "items": ["Renovar el pasaporte", "Seguro"], "list": "todo"},
        headers=WRITE,
    )
    first = added.json()["content"]["todo"][0]["item_id"]
    await api.post("/tools/check_item", json={"item_id": first}, headers=WRITE)
    read = await api.post(
        "/tools/get_trip", json={"trip_id": trip["id"], "include": ["checklist"]}, headers=WRITE
    )

    content = read.json()["content"]["checklist"]
    assert content["packing"] == []
    assert [(i["text"], i["checked"]) for i in content["todo"]] == [
        ("Renovar el pasaporte", True),
        ("Seguro", False),
    ]
