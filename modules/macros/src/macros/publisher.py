from __future__ import annotations

from uuid import UUID

import httpx

from arga_contracts import notify
from arga_contracts import records as fichas
from arga_module.db import engine
from arga_module.publisher import Publisher
from macros import notices, records, templates

MODULE = "macros"

RECORDS = fichas.Every()
NOTICES = fichas.Every(300)


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        for every in (RECORDS, NOTICES):
            every.forget(user)
    await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
    await notify.refresh(client, engine, MODULE, notices.build, NOTICES, user)
    async with PUBLISHER.as_module() as connection:
        await templates.materialise(connection, client)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
