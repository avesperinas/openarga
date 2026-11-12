from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import text

from arga_contracts import metrics as cifras
from arga_contracts import records as fichas
from arga_tenancy import as_user, people
from money import book as books
from money import common, metrics, publisher
from money.db import engine

MODULE = "money"
ALIVE = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.alive"))
INTERVAL = float(os.environ.get("WORKER_INTERVAL_SECONDS", "30"))
METRICS = fichas.Every()


def beat() -> None:
    ALIVE.touch()


KEEPS = text("""
    select exists (select 1 from money.money_v1_setting where space_id is not null)
       and exists (select 1 from money.money_v1_account where shared_space)
""")


async def keep_common(user) -> int:
    async with engine().begin() as connection:
        await connection.execute(text(f'set local role "mod_{MODULE}"'))
        if not await connection.scalar(KEEPS):
            return 0
        lo = await books.load(connection, user)
        return await common.publish(connection, lo, date.today())


async def run_once(client: httpx.AsyncClient) -> dict[str, int]:
    total = {"published": 0, "pending": 0}
    for user, spaces in await people(client):
        with as_user(user, spaces):
            await cifras.refresh(engine, MODULE, metrics.build, METRICS, user, client)
            try:
                await keep_common(user)
            except Exception as error:  # noqa: BLE001 - lo común no para las cifras ni la cola
                print(f"money worker · común: {type(error).__name__}: {error}", file=sys.stderr)
            async with engine().begin() as connection:
                await connection.execute(text(f'set local role "mod_{MODULE}"'))
                result = await publisher.publish_pending(connection, client)
        total["published"] += result["published"]
        total["pending"] += result["pending"]
    return total


async def loop() -> None:  # pragma: no cover -- el bucle de siempre
    async with httpx.AsyncClient() as client:
        while True:
            beat()
            try:
                result = await run_once(client)
                if result["published"]:
                    print(f"money worker · {result['published']} publicado(s)", flush=True)
            except Exception as error:  # noqa: BLE001 - un fallo no tumba el proceso
                print(
                    f"money worker · {type(error).__name__}: {error}", file=sys.stderr, flush=True
                )
            await asyncio.sleep(INTERVAL)


def main() -> None:  # pragma: no cover
    print("money worker: publica sus cifras (ADR-0087)", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(loop())


if __name__ == "__main__":
    main()
