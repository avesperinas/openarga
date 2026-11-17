from __future__ import annotations

import os
from uuid import UUID

import httpx

from arga_contracts import notify
from arga_contracts import records as kit
from arga_module.db import engine
from arga_module.publisher import Publisher
from goals import figures, goals, notices, records

MODULE = "goals"
SETTLE_INTERVAL_SECONDS = float(os.environ.get("SETTLE_INTERVAL_SECONDS", "600"))

RECORDS = kit.Every()
NOTICES = kit.Every(300)
SETTLE = kit.Every(SETTLE_INTERVAL_SECONDS)
HISTORY: set[UUID] = set()


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        RECORDS.forget(user)
        NOTICES.forget(user)
    await kit.refresh(client, engine, MODULE, records.build, RECORDS, user)
    await notify.refresh(client, engine, MODULE, notices.build, NOTICES, user)
    if user not in HISTORY:
        async with PUBLISHER.as_module() as connection:
            await figures.backfill(connection)
        HISTORY.add(user)
    if SETTLE.due(user):
        async with PUBLISHER.as_module() as connection:
            if closed := await goals.settle(connection):
                print(f"publisher · {len(closed)} goal(s) closed", flush=True)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
