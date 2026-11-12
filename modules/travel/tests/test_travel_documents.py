from __future__ import annotations

from travel_kit import BRUGES, make_trip, stay

WRITE = {"x-arga-scopes": "travel:read travel:write"}
PDF = b"%PDF-1.4\n% billete sintetico\n"


async def test_a_ticket_is_stored_linked_to_its_booking_and_given_back_as_it_was(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    hotel = (await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12"))["stays"][0]

    uploaded = await api.post(
        f"/trips/{trip['id']}/documents",
        params={"name": "Reserva hotel.pdf", "link_type": "stay", "link_id": hotel["id"]},
        content=PDF,
        headers={"content-type": "application/pdf"},
    )
    [document] = uploaded.json()
    read = await api.get(f"/trips/{trip['id']}/documents/{document['id']}/file")

    assert uploaded.status_code == 201, uploaded.text
    assert (document["name"], document["size"], document["link"]["type"]) == (
        "Reserva hotel.pdf",
        len(PDF),
        "stay",
    )
    assert document["link"]["title"] == "Brujas"
    assert read.content == PDF
    assert read.headers["content-type"] == "application/pdf"


async def test_a_link_to_another_trip_or_an_empty_file_is_refused(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    other = await make_trip(api, "Otra", "2025-05-10", "2025-05-12")
    foreign = (await stay(api, other["id"], BRUGES, "2025-05-10", "2025-05-12"))["stays"][0]

    wrong = await api.post(
        f"/trips/{trip['id']}/documents",
        params={"name": "x.pdf", "link_type": "stay", "link_id": foreign["id"]},
        content=PDF,
    )
    empty = await api.post(f"/trips/{trip['id']}/documents", params={"name": "x.pdf"}, content=b"")

    assert wrong.status_code == 404
    assert empty.status_code == 409
    assert (await api.get(f"/trips/{trip['id']}/documents")).json() == []


async def test_removing_the_booking_keeps_the_document_unlinked(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    hotel = (await stay(api, trip["id"], BRUGES, "2025-04-10", "2025-04-12"))["stays"][0]
    [document] = (
        await api.post(
            f"/trips/{trip['id']}/documents",
            params={"name": "hotel.pdf", "link_type": "stay", "link_id": hotel["id"]},
            content=PDF,
        )
    ).json()

    await api.delete(f"/trips/{trip['id']}/stays/{hotel['id']}")
    renamed = await api.patch(
        f"/trips/{trip['id']}/documents/{document['id']}", json={"name": "Hotel Brujas.pdf"}
    )

    assert [(d["name"], d["link"]) for d in renamed.json()] == [("Hotel Brujas.pdf", None)]


async def test_claude_sees_that_the_ticket_is_there_not_what_it_says(api) -> None:
    trip = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    await api.post(
        f"/trips/{trip['id']}/documents",
        params={"name": "Seguro.pdf"},
        content=PDF,
        headers={"content-type": "application/pdf"},
    )

    told = await api.post(
        "/tools/get_trip", json={"trip_id": trip["id"], "include": ["documents"]}, headers=WRITE
    )

    assert told.json()["content"]["documents"] == [
        {"name": "Seguro.pdf", "content_type": "application/pdf", "size_kb": 0, "for": None}
    ]
    assert "PDF-1.4" not in told.text
