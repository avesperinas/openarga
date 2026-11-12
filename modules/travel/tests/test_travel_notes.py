from __future__ import annotations

from uuid import uuid4

from travel_kit import make_trip

WRITE = {"x-arga-scopes": "travel:read travel:write"}


async def test_notes_keep_their_order_category_and_markdown(api) -> None:
    trip = await make_trip(api, "Japón", "2027-11-01", "2027-11-14", status="plan")
    same = str(uuid4())
    await api.post(
        f"/trips/{trip['id']}/notes",
        json={"id": same, "title": "Visado", "category": "visa", "body": "Sin visado **90 días**."},
    )
    again = await api.post(
        f"/trips/{trip['id']}/notes", json={"id": same, "title": "Visado", "category": "visa"}
    )
    listed = (
        await api.post(
            f"/trips/{trip['id']}/notes",
            json={"title": "Propinas", "category": "culture", "body": "No se dejan."},
        )
    ).json()
    wrong = await api.post(f"/trips/{trip['id']}/notes", json={"title": "X", "category": "food"})

    assert len(again.json()) == 1
    assert [(n["title"], n["category"], n["position"]) for n in listed] == [
        ("Visado", "visa", 0),
        ("Propinas", "culture", 1),
    ]
    assert listed[0]["body"] == "Sin visado **90 días**."
    assert wrong.status_code == 422


async def test_claude_notes_and_corrects_only_what_it_says(api) -> None:
    trip = await make_trip(api, "Japón", "2027-11-01", "2027-11-14", status="plan")
    added = await api.post(
        "/tools/add_trip_note",
        json={
            "trip_id": trip["id"],
            "title": "Vacunas",
            "category": "health",
            "body": "Ninguna obligatoria.",
        },
        headers=WRITE,
    )
    note_id = added.json()["content"]["notes"][0]["note_id"]
    fixed = await api.post(
        "/tools/update_trip_note", json={"note_id": note_id, "title": "Salud"}, headers=WRITE
    )
    read = await api.post(
        "/tools/get_trip", json={"trip_id": trip["id"], "include": ["notes"]}, headers=WRITE
    )

    [note] = read.json()["content"]["trip_notes"]
    assert fixed.status_code == 200, fixed.text
    assert (note["title"], note["category"], note["body"]) == (
        "Salud",
        "health",
        "Ninguna obligatoria.",
    )
