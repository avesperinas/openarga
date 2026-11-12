from __future__ import annotations

import os
import sys
from uuid import UUID

import httpx

from arga_contracts import notify as avisos
from arga_contracts import records as fichas
from arga_module.db import engine
from arga_module.publisher import Publisher
from planner import apps, feeds, notices, records

MODULE = "planner"

RECORDS = fichas.Every()
NOTICES = fichas.Every(60)
DERIVE = fichas.Every(float(os.environ.get("DERIVE_INTERVAL_SECONDS", "60")))


async def derive(user: UUID) -> dict[str, int]:
    total = {"changed": 0, "removed": 0, "layers": 0}
    try:
        async with PUBLISHER.as_module() as connection:
            for result in (await feeds.derive(connection), await apps.derive(connection)):
                for key, value in result.items():
                    total[key] = total.get(key, 0) + value
    except Exception as error:  # noqa: BLE001 - el reflejo no para lo que publica Planner
        print(f"reflejo · {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return total
    if any(total.values()):
        print(f"reflejo · {total}", flush=True)
    return total


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        for every in (RECORDS, NOTICES):
            every.forget(user)
    if DERIVE.due(user):
        await derive(user)
    await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
    await avisos.refresh(client, engine, MODULE, notices.build, NOTICES, user)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
