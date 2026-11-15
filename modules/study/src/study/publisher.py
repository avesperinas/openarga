from __future__ import annotations

from uuid import UUID

import httpx

from arga_contracts import metrics as published_metrics
from arga_contracts import notify as notices_contract
from arga_contracts import records as records_contract
from arga_module.db import engine
from arga_module.publisher import Publisher
from arga_tenancy import as_user
from study import metrics, notices, outbox, records

MODULE = "study"

RECORDS = records_contract.Every()
NOTICES = records_contract.Every()
METRICS = records_contract.Every()
REPUBLISHED: set[UUID] = set()


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        for every in (RECORDS, NOTICES, METRICS):
            every.forget(user)
    await records_contract.refresh(client, engine, MODULE, records.build, RECORDS, user)
    await notices_contract.refresh(client, engine, MODULE, notices.build, NOTICES, user)
    await published_metrics.refresh(engine, MODULE, metrics.build, METRICS, user)
    if user not in REPUBLISHED:
        with as_user(user):
            async with PUBLISHER.as_module() as connection:
                await outbox.republish(connection)
        REPUBLISHED.add(user)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
