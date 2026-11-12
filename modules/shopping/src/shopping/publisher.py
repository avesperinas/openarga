from __future__ import annotations

from uuid import UUID

import httpx

from arga_contracts import records as fichas
from arga_module.db import engine
from arga_module.publisher import Publisher
from shopping import records, shopping

MODULE = "shopping"

BACKFILLED: set = set()

RECORDS = fichas.Every()


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        RECORDS.forget(user)
    await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
    if user not in BACKFILLED:
        async with PUBLISHER.as_module() as connection:
            await shopping.backfill(connection)
        BACKFILLED.add(user)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
