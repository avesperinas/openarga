from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

import asyncpg
import httpx
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from arga_module.db import database_url
from arga_tenancy import USER_HEADER, as_user, current_user, kernel_url, users

SOURCE = "app"
BATCH = 50
BATCHES = 10
TICK_SECONDS = float(os.environ.get("PUBLISH_TICK_SECONDS", "30"))
SETTLE_SECONDS = 0.2
RETRY_SECONDS = 5.0
RECONNECT_SECONDS = 5.0
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.alive"))
DERIVED = ("record", "metric")

Refresh = Callable[[httpx.AsyncClient, UUID, bool], Awaitable[object]]


def listen_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


class Publisher:
    def __init__(
        self,
        module: str,
        engine: Callable[[], AsyncEngine],
        refresh: Refresh | None = None,
    ) -> None:
        self.module = module
        self.engine = engine
        self.refresh = refresh
        self.role = f"mod_{module}"
        self.channel = f"{module}_outbox"
        outbox = f"{module}.{module}_outbox"
        self._pending = text(f"""
            select id, type, ts, payload, dedup_hash, user_id
            from {outbox}
            where published_at is null
            order by id
            limit :batch
            for update skip locked
        """)
        self._failed = text(
            f"update {outbox} set attempts = attempts + 1, last_error = :error where id = :id"
        )
        self._done = text(
            f"update {outbox} set published_at = now(), attempts = attempts + 1, "
            "last_error = null where id = :id"
        )
        self._fresh = text(
            f"select exists (select 1 from {outbox} where published_at is null "
            "and type not in :derived)"
        ).bindparams(bindparam("derived", expanding=True))
        self._derived = [f"{module}.{kind}" for kind in DERIVED]
        self._lock = text("select pg_try_advisory_xact_lock(hashtext(:channel), hashtext(:user))")
        self._touched: set[UUID] = set()
        self._wake: asyncio.Event | None = None

    def touch(self, user: UUID) -> None:
        self._touched.add(user)
        if self._wake is not None:
            self._wake.set()

    @contextlib.asynccontextmanager
    async def as_module(self):
        async with self.engine().begin() as connection:
            await connection.execute(text(f'set local role "{self.role}"'))
            yield connection

    async def publish_pending(
        self, connection: AsyncConnection, client: httpx.AsyncClient
    ) -> dict[str, int]:
        rows = (await connection.execute(self._pending, {"batch": BATCH})).all()
        published = 0
        for row in rows:
            event = {
                "ts": row.ts.isoformat(),
                "module": self.module,
                "source": SOURCE,
                "type": row.type,
                "payload": row.payload,
                "dedup_hash": row.dedup_hash,
            }
            owner = row.user_id or current_user.get()
            headers = {USER_HEADER: str(owner)} if owner else {}
            try:
                response = await client.post(
                    f"{kernel_url()}/events", json=event, headers=headers, timeout=10.0
                )
                response.raise_for_status()
            except httpx.HTTPError as error:
                await connection.execute(
                    self._failed, {"error": f"{type(error).__name__}: {error}"[:500], "id": row.id}
                )
                return {"published": published, "pending": len(rows) - published}
            await connection.execute(self._done, {"id": row.id})
            published += 1
        return {"published": published, "pending": len(rows) - published}

    async def run_once(self, client: httpx.AsyncClient) -> dict[str, int]:
        total = {"published": 0, "pending": 0, "more": 0}
        for user in await users(client):
            with as_user(user):
                if self.refresh is not None:
                    touched = user in self._touched
                    self._touched.discard(user)
                    async with self.as_module() as connection:
                        fresh = touched or bool(
                            await connection.scalar(self._fresh, {"derived": self._derived})
                        )
                    await self.refresh(client, user, fresh)
                for _ in range(BATCHES):
                    async with self.as_module() as connection:
                        mine = await connection.scalar(
                            self._lock, {"channel": self.channel, "user": str(user)}
                        )
                        if not mine:
                            result = {"published": 0, "pending": 0}
                            break
                        result = await self.publish_pending(connection, client)
                    total["published"] += result["published"]
                    total["pending"] += result["pending"]
                    if result["pending"] or result["published"] < BATCH:
                        break
                else:
                    total["more"] += 1
        return total

    async def listen(self, wake: Callable[[], None]) -> None:
        while True:
            lost = asyncio.Event()
            connection = None
            try:
                connection = await asyncpg.connect(listen_dsn(database_url()))
                connection.add_termination_listener(lambda _, lost=lost: lost.set())
                await connection.add_listener(self.channel, lambda *_: wake())
                wake()
                await lost.wait()
            except Exception as error:  # noqa: BLE001 - sin avisos se sigue con la pasada de seguridad
                print(
                    f"publisher · sin avisos: {type(error).__name__}: {error}",
                    file=sys.stderr,
                    flush=True,
                )
            finally:
                if connection is not None and not connection.is_closed():
                    await connection.close()
            await asyncio.sleep(RECONNECT_SECONDS)

    async def loop(self, client: httpx.AsyncClient) -> None:
        wake = asyncio.Event()
        self._wake = wake
        listener = asyncio.create_task(self.listen(wake.set))
        failures = 0
        try:
            while True:
                HEARTBEAT.touch()  # noqa: ASYNC240
                wake.clear()
                more = False
                try:
                    result = await self.run_once(client)
                    more = bool(result["more"])
                    if result["pending"]:
                        failures += 1
                        print(
                            f"publisher · {result['pending']} pendiente(s), reintento", flush=True
                        )
                    else:
                        failures = 0
                        if result["published"]:
                            print(f"publisher · {result['published']} publicado(s)", flush=True)
                except Exception as error:  # noqa: BLE001 - un fallo de base no tumba el proceso
                    failures += 1
                    print(
                        f"publisher · {type(error).__name__}: {error}", file=sys.stderr, flush=True
                    )
                if more and not failures:
                    continue
                delay = (
                    min(60.0, RETRY_SECONDS * (2 ** min(failures, 4))) if failures else TICK_SECONDS
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(wake.wait(), delay)
                    await asyncio.sleep(SETTLE_SECONDS)
        finally:
            listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listener

    async def _standalone(self) -> None:
        async with httpx.AsyncClient() as client:
            await self.loop(client)

    def main(self) -> int:
        print(f"publisher · {self.module} → {kernel_url()}", flush=True)
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(self._standalone())
        return 0
