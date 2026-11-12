from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text
from travel_kit import make_trip

import arga_contracts as contracts
from arga_tenancy import as_user
from travel import records
from travel.db import engine

WRITE = {"x-arga-scopes": "travel:read travel:write"}
READ = {"x-arga-scopes": "travel:read"}
OTHER = UUID("00000000-0000-4000-8000-00000000b0b0")


async def test_the_day_is_written_whole_and_twice_is_once(api) -> None:
    trip = await make_trip(api, "Lisboa", "2025-05-01", "2025-05-04")
    same = str(uuid4())
    first = await api.put(
        f"/trips/{trip['id']}/journal/2025-05-02", json={"id": same, "body": "Tranvía 28."}
    )
    again = await api.put(
        f"/trips/{trip['id']}/journal/2025-05-02", json={"id": same, "body": "Tranvía 28."}
    )
    changed = await api.put(
        f"/trips/{trip['id']}/journal/2025-05-02", json={"body": "  Tranvía 28 y pasteles.  "}
    )
    outside = await api.put(f"/trips/{trip['id']}/journal/2025-06-01", json={"body": "No."})

    assert first.status_code == 200, first.text
    assert again.json() == first.json()
    [day] = changed.json()
    assert (day["day"], day["body"], day["id"]) == ("2025-05-02", "Tranvía 28 y pasteles.", same)
    assert outside.status_code == 409
    assert "fuera del viaje" in outside.json()["detail"]

    gone = await api.put(f"/trips/{trip['id']}/journal/2025-05-02", json={"body": "   "})
    assert gone.json() == []
    assert (await api.get(f"/trips/{trip['id']}/journal")).json() == []


async def test_today_brings_what_is_written_today(api) -> None:
    trip = await make_trip(api, "Lisboa", "2025-05-01", "2025-05-04")
    await api.put(f"/trips/{trip['id']}/journal/2025-05-03", json={"body": "Sintra con niebla."})

    found = (await api.get("/today", params={"day": "2025-05-03"})).json()
    other = (await api.get("/today", params={"day": "2025-05-04"})).json()

    assert found["journal"] == "Sintra con niebla."
    assert other["journal"] is None


async def test_claude_adds_a_paragraph_and_reads_it_back(api) -> None:
    trip = await make_trip(api, "Lisboa", "2025-05-01", "2025-05-04")
    one = await api.post(
        "/tools/write_journal",
        json={"trip_id": trip["id"], "day": "2025-05-02", "text": "Belém por la mañana."},
        headers=WRITE,
    )
    two = await api.post(
        "/tools/write_journal",
        json={"trip_id": trip["id"], "day": "2025-05-02", "text": "Cena en Alfama."},
        headers=WRITE,
    )
    read = await api.post("/tools/get_trip", json={"trip_id": trip["id"]}, headers=READ)
    replaced = await api.post(
        "/tools/write_journal",
        json={"trip_id": trip["id"], "day": "2025-05-02", "text": "Todo.", "mode": "replace"},
        headers=WRITE,
    )
    outside = await api.post(
        "/tools/write_journal",
        json={"trip_id": trip["id"], "day": "2025-07-01", "text": "No."},
        headers=WRITE,
    )
    refused = await api.post(
        "/tools/write_journal",
        json={"trip_id": trip["id"], "day": "2025-05-02", "text": "No."},
        headers=READ,
    )

    assert one.status_code == 200, one.text
    assert two.json()["content"]["journal"] == [
        {"day": "2025-05-02", "text": "Belém por la mañana.\n\nCena en Alfama."}
    ]
    assert read.json()["content"]["journal"] == two.json()["content"]["journal"]
    assert replaced.json()["content"]["journal"] == [{"day": "2025-05-02", "text": "Todo."}]
    assert outside.json()["content"]["code"] == "DATE_OUT_OF_RANGE"
    assert refused.status_code == 403


async def test_it_reaches_the_day_note_and_is_only_its_author_s(api, schema) -> None:
    trip = await make_trip(api, "Lisboa", "2025-05-01", "2025-05-04")
    await api.put(f"/trips/{trip['id']}/journal/2025-05-02", json={"body": "Tranvía 28."})

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        found = {one["id"]: one for one in await records.build(connection)}
    entry = found[f"journal:{trip['id']}:2025-05-02"]
    assert entry == contracts.record(**entry)
    assert (entry["day"], entry["kind"], entry["body"]) == ("2025-05-02", "Diario", "Tranvía 28.")
    assert entry["title"] == "Diario · Lisboa"
    assert entry["href"] == f"/travel/viajes/{trip['id']}/diario"

    with as_user(OTHER):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_travel"'))
            seen = await connection.scalar(text("select count(*) from travel.travel_journal"))
    assert seen == 0
