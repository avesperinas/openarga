from __future__ import annotations

from uuid import UUID

import httpx

from arga_contracts import metrics as cifras
from arga_contracts import records as fichas
from arga_module.db import engine
from arga_module.publisher import Publisher
from arga_tenancy import as_user
from travel import covers, itinerary, metrics, plans, records, travel

MODULE = "travel"

BACKFILLED: set[UUID] = set()

RECORDS = fichas.Every()
METRICS = fichas.Every()
SHARED = fichas.Every()


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        for every in (RECORDS, METRICS, SHARED):
            every.forget(user)
    await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
    await cifras.refresh(engine, MODULE, metrics.build, METRICS, user)
    with as_user(user, await fichas.spaces(client)):
        async with PUBLISHER.as_module() as connection:
            if user not in BACKFILLED:
                await itinerary.ensure_blocks(connection)
                await travel.backfill(connection)
                BACKFILLED.add(user)
            if SHARED.due(user):
                await travel.sync_shared(connection)
            await covers.fill(connection)
            await plans.refresh(connection)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
