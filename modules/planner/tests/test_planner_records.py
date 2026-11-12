from __future__ import annotations

from sqlalchemy import text
from test_planner_events import at, create

import arga_contracts as contracts
from planner import records
from planner.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_planner"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_each_day_with_your_events_goes_to_its_note(api) -> None:
    await api.get("/calendars")
    await create(
        api,
        title="Dentista",
        start=at("2026-09-29T16:00"),
        end=at("2026-09-29T17:30"),
        location="Calle Sintética 1",
    )
    await create(api, title="Fiesta", all_day=True, start="2026-09-29", end="2026-09-30")
    await create(
        api,
        title="Inglés",
        start=at("2026-09-01T19:00"),
        end=at("2026-09-01T20:00"),
        rrule="FREQ=WEEKLY;COUNT=3",
    )

    found = await built()

    assert found["day:2026-09-29"]["body"] == (
        "- Todo el día · Fiesta\n- 16:00–17:30 · Dentista · Calle Sintética 1"
    )
    assert found["day:2026-09-29"]["properties"] == {"eventos": 2}
    assert [day for day in found if "Inglés" in found[day]["body"]] == [
        "day:2026-09-01",
        "day:2026-09-08",
        "day:2026-09-15",
    ]
