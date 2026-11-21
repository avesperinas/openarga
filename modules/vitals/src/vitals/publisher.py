from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import metrics as cifras
from arga_contracts import notify as avisos
from arga_contracts import records as fichas
from arga_module.publisher import BATCH as SHARED_BATCH
from arga_module.publisher import Publisher
from arga_tenancy import as_user, users
from vitals import metrics, notices, records, weight
from vitals.db import engine

MODULE = "vitals"
SOURCE = "app"
INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "5"))
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.alive"))


def kernel_url() -> str:
    return os.environ.get("KERNEL_URL", "http://kernel:8000").rstrip("/")


SHARED = Publisher(MODULE, engine)
DRAIN = 10


async def publish_pending(connection: AsyncConnection, client: httpx.AsyncClient) -> dict[str, int]:
    # The shared publisher sends a batch in one request; a person's first pass can queue thousands
    # of points, so it drains several batches instead of one every few seconds.
    total = {"published": 0, "pending": 0}
    for _ in range(DRAIN):
        result = await SHARED.publish_pending(connection, client)
        total["published"] += result["published"]
        total["pending"] += result["pending"]
        if result["pending"] or result["published"] < SHARED_BATCH:
            break
    return total


BACKFILLED: set = set()


RECORDS = fichas.Every()
METRICS = fichas.Every()
NOTICES = fichas.Every()


async def run_once(client: httpx.AsyncClient) -> dict[str, int]:
    total = {"published": 0, "pending": 0}
    for user in await users(client):
        with as_user(user):
            await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
            await cifras.refresh(engine, MODULE, metrics.build, METRICS, user)
            await avisos.refresh(client, engine, MODULE, notices.build, NOTICES, user)
            async with engine().begin() as connection:
                await connection.execute(text('set local role "mod_vitals"'))
                if user not in BACKFILLED:
                    await weight.backfill(connection)
                    BACKFILLED.add(user)
                result = await publish_pending(connection, client)
        total["published"] += result["published"]
        total["pending"] += result["pending"]
    return total


async def loop() -> None:
    failures = 0
    async with httpx.AsyncClient() as client:
        while True:
            HEARTBEAT.touch()  # noqa: ASYNC240
            try:
                result = await run_once(client)
                if result["pending"]:
                    failures += 1
                    print(f"publisher · {result['pending']} pending, retrying", flush=True)
                else:
                    failures = 0
                    if result["published"]:
                        print(f"publisher · {result['published']} published", flush=True)
            except Exception as error:  # noqa: BLE001 - a database failure does not bring the process down
                failures += 1
                print(f"publisher · {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            await asyncio.sleep(min(60.0, INTERVAL_SECONDS * (2 ** min(failures, 4))))


def main() -> int:
    print(f"publisher · vitals → {kernel_url()} cada {INTERVAL_SECONDS:g} s", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
