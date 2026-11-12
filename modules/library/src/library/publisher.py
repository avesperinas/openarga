from __future__ import annotations

from uuid import UUID

import httpx

from arga_contracts import metrics as cifras
from arga_contracts import records as fichas
from arga_module.db import engine
from arga_module.publisher import Publisher
from library import metrics, records

MODULE = "library"

RECORDS = fichas.Every()
METRICS = fichas.Every()


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        RECORDS.forget(user)
        METRICS.forget(user)
    await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
    await cifras.refresh(engine, MODULE, metrics.build, METRICS, user)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
