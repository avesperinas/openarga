from __future__ import annotations

from outings_world import make_wish
from sqlalchemy import text

import arga_contracts as contracts
from outings import metrics
from outings.db import engine


async def built() -> list[dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_outings"'))
        found = await metrics.build(connection)
    for one in found:
        assert one == contracts.metric("outings", **one)
    return found


async def test_a_wish_done_counts_its_day_and_restoring_it_takes_it_back(api) -> None:
    first = await make_wish(api)
    second = await make_wish(api, "Bardenas")
    await make_wish(api, "Pendiente")
    await api.post(f"/wishes/{first['id']}/done")
    await api.post(f"/wishes/{second['id']}/done")

    [done] = await built()
    assert done["key"] == "outings.wishes_done" and done["value"] == 2

    await api.post(f"/wishes/{second['id']}/restore")
    [done] = await built()
    assert done["value"] == 1
