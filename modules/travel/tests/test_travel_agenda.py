from __future__ import annotations

from sqlalchemy import text
from travel_kit import make_trip

import arga_agenda
from travel import travel


async def outbox(schema) -> list[dict]:
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        rows = await connection.execute(
            text("select payload from travel.travel_outbox where type = 'travel.trip' order by id")
        )
        return [row.payload for row in rows]


async def test_a_trip_is_a_run_of_whole_days(api, schema) -> None:
    trip = await make_trip(api, starts="2025-04-10", ends="2025-04-15")

    item = arga_agenda.check_event((await outbox(schema))[-1])
    assert item["uid"] == f"travel:trip:{trip['id']}"
    assert item["all_day"] is True
    assert (item["start"], item["end"]) == ("2025-04-10", "2025-04-16")
    assert item["href"] == f"/travel/viajes/{trip['id']}"


async def test_deleting_a_trip_takes_it_out_of_the_calendar(api, schema) -> None:
    trip = await make_trip(api)
    assert (await api.delete(f"/trips/{trip['id']}")).status_code == 204

    last = (await outbox(schema))[-1]
    assert last["agenda"]["uid"] == f"travel:trip:{trip['id']}"
    assert last["agenda"]["status"] == "cancelled"


async def test_the_trips_of_before_are_published_once(api, schema) -> None:
    await make_trip(api, title="Flandes")
    await make_trip(api, title="Roma", starts="2025-06-01", ends="2025-06-05")
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        await connection.execute(text("delete from travel.travel_outbox"))

    for _ in range(2):
        async with schema.begin() as connection:
            await connection.execute(text('set local role "mod_travel"'))
            await travel.backfill(connection)

    assert len(await outbox(schema)) == 2
