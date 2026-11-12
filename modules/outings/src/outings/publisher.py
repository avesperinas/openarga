from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx

from arga_contracts import metrics as cifras
from arga_contracts import notify as avisos
from arga_contracts import records as fichas
from arga_module.db import engine
from arga_module.publisher import Publisher
from outings import agenda, foryou, metrics, photos, places, records, weekly

MODULE = "outings"

LOCATE_EVERY = float(os.environ.get("LOCATE_EVERY_SECONDS", "60"))
LOCATED: dict[object, float] = {}

RECORDS = fichas.Every()
METRICS = fichas.Every()
NOTICES = fichas.Every()


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if fresh:
        for every in (RECORDS, METRICS, NOTICES):
            every.forget(user)
    async with PUBLISHER.as_module() as connection:
        await agenda.derive(connection)
        if time.monotonic() - LOCATED.get(user, -LOCATE_EVERY) >= LOCATE_EVERY:
            LOCATED[user] = time.monotonic()
            await places.locate(connection)
            await photos.fill(connection)
    if weekly.due(user):
        async with PUBLISHER.as_module() as connection:
            asked = await weekly.ask(connection, datetime.now(UTC))
        if asked and asked.get("outcome") == "queued":
            print(f"publisher · agenda de la semana pedida a tu Claude ({user})", flush=True)
    await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
    await cifras.refresh(engine, MODULE, metrics.build, METRICS, user)
    await avisos.refresh(client, engine, MODULE, foryou.build, NOTICES, user)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
