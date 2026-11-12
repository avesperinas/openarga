from __future__ import annotations

from sqlalchemy import text
from travel_kit import BRUGES, LILLE, MADRID, make_trip, stay

import arga_contracts as contracts
from travel import metrics
from travel.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_travel"'))
        found = await metrics.build(connection)
    for one in found:
        assert one == contracts.metric("travel", **one)
    return {contracts.metric_identity(one): one for one in found}


async def test_countries_grow_when_a_trip_ends_and_each_day_away_counts(api) -> None:
    first = await make_trip(api, "Flandes", "2025-04-10", "2025-04-12")
    await stay(api, first["id"], BRUGES, "2025-04-10", "2025-04-12")
    second = await make_trip(api, "Lille", "2025-06-01", "2025-06-02")
    await stay(api, second["id"], LILLE, "2025-06-01", "2025-06-02")
    third = await make_trip(api, "Madrid", "2025-07-01", "2025-07-01")
    await stay(api, third["id"], MADRID, "2025-07-01", "2025-07-01")

    found = await built()

    assert found["travel.countries@2025-04-12"]["value"] == 1
    assert found["travel.countries@2025-06-02"]["value"] == 2
    assert found["travel.countries@2025-07-01"]["value"] == 3
    days = [key for key in found if key.startswith("travel.days_away@")]
    assert len(days) == 6
