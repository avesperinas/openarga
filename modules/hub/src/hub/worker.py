from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from arga_contracts import notify as avisos
from arga_contracts.records import Every
from arga_module.schedule import Schedule
from arga_tenancy import as_user, kernel_url, users
from hub import capabilities, catalogue, credentials, notices, sync
from hub.db import as_module, engine

MODULE = "hub"
NOTICES = Every()
CONCURRENCY = int(os.environ.get("WORKER_CONCURRENCY", "4"))
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.alive"))

RUNNABLE = text("""
    select c.id, c.provider, c.label, c.config, c.consent_expires_at,
           exists (select 1 from hub.hub_run r where r.connection_id = c.id) as ran
    from hub.hub_connection c
    where c.status = 'active' and not c.paused
    order by c.created_at
""")

SCHEDULES = {
    provider.id: Schedule.parse(provider.schedule)
    for provider in catalogue.PROVIDERS
    if provider.schedule and provider.id in sync.CLIENTS
}


def say(line: str) -> None:
    print(f"worker {MODULE} · {line}", flush=True)


def beat() -> None:
    HEARTBEAT.touch()


def due(rows: Sequence[Any], moment: datetime, everything: bool) -> list[Any]:
    return [
        row
        for row in rows
        if row.provider in SCHEDULES
        and (everything or not row.ran or SCHEDULES[row.provider].matches(moment))
    ]


async def runnable(moment: datetime, everything: bool) -> list[Any]:
    async with as_module() as database:
        rows = list((await database.execute(RUNNABLE)).all())
        scheduled = {row.id for row in due(rows, moment, everything)}
        chosen = []
        for row in rows:
            client = sync.CLIENTS.get(row.provider)
            if client is None:
                continue
            if row.id in scheduled:
                if client.should_run is None or await client.should_run(database, row, moment):
                    chosen.append(row)
            elif client.urgent is not None and await client.urgent(database, row, moment):
                chosen.append(row)
        return chosen


async def tick(
    moment: datetime,
    everything: bool,
    *,
    people: Callable[[], Awaitable[list[UUID]]],
    source: httpx.AsyncClient,
    kernel: httpx.AsyncClient,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, dict[str, str]]:
    try:
        everyone = await people()
    except httpx.HTTPError as error:
        say(f"el kernel no dice quién existe ({type(error).__name__}); sin pasada")
        return {}
    results: dict[str, dict[str, str]] = {}
    limit = asyncio.Semaphore(CONCURRENCY)
    people_at_once = asyncio.Semaphore(CONCURRENCY)

    async def one(user: UUID, connection: Any) -> None:
        async with limit:
            beat()
            try:
                outcome = await sync.run(connection, source=source, kernel=kernel, sleep=sleep)
            except SQLAlchemyError as error:
                say(f"sin base de datos a mitad de pasada ({type(error).__name__})")
                return
            except Exception as error:  # noqa: BLE001 - una pasada rota no para a las que corren
                say(f"{connection.label}: {type(error).__name__}: {error}")
                return
            results.setdefault(str(user), {})[connection.label] = outcome.outcome

    async def person(user: UUID) -> None:
        async with people_at_once:
            with as_user(user):
                try:
                    pending = await runnable(moment, everything)
                except SQLAlchemyError as error:
                    say(f"no se pueden leer las conexiones ({type(error).__name__})")
                    return
                await asyncio.gather(*(one(user, connection) for connection in pending))
                try:
                    rechecked = await capabilities.maps_recheck(source)
                except SQLAlchemyError as error:
                    say(f"no se puede mirar Protomaps ({type(error).__name__})")
                else:
                    if rechecked:
                        results.setdefault(str(user), {})["Protomaps"] = rechecked
                await avisos.refresh(kernel, engine, MODULE, notices.build, NOTICES, user)

    await asyncio.gather(*(person(user) for user in everyone))
    return {user: results[user] for user in map(str, everyone) if user in results}


async def serve() -> None:
    async with (
        httpx.AsyncClient(timeout=30.0) as source,
        httpx.AsyncClient(base_url=kernel_url(), timeout=30.0) as kernel,
    ):

        async def people() -> list[UUID]:
            return await users(kernel)

        beat()
        say(f"calendarios: {', '.join(f'{p} ({s.expression})' for p, s in SCHEDULES.items())}")
        now = datetime.now(UTC).replace(second=0, microsecond=0)
        say(f"al arrancar: {await tick(now, True, people=people, source=source, kernel=kernel)}")
        last = now
        while True:
            beat()
            now = datetime.now(UTC).replace(second=0, microsecond=0)
            if now != last:
                last = now
                done = await tick(now, False, people=people, source=source, kernel=kernel)
                if done:
                    say(f"{now:%Y-%m-%d %H:%M}: {done}")
            await asyncio.sleep(20)


def main() -> int:
    try:
        credentials.masters()
    except Exception as error:  # noqa: BLE001 - se dice y se sale con código distinto de cero
        print(f"worker {MODULE}: {error}", file=sys.stderr)
        return 1
    asyncio.run(serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
