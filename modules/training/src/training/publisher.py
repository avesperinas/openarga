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
from arga_contracts import records as fichas
from arga_tenancy import USER_HEADER, as_user, current_user, users
from training import activities, agenda, bodyweight, links, metrics, records, workouts
from training.db import engine

MODULE = "training"
SOURCE = "app"
BATCH = 50
INTERVAL_SECONDS = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "5"))
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.alive"))

PENDING = text("""
    select id, type, ts, payload, dedup_hash, user_id
    from training.training_outbox
    where published_at is null
    order by id
    limit :batch
    for update skip locked
""")


def kernel_url() -> str:
    return os.environ.get("KERNEL_URL", "http://kernel:8000").rstrip("/")


async def publish_pending(connection: AsyncConnection, client: httpx.AsyncClient) -> dict[str, int]:
    rows = (await connection.execute(PENDING, {"batch": BATCH})).all()
    published = 0
    for row in rows:
        event = {
            "ts": row.ts.isoformat(),
            "module": MODULE,
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
                text(
                    "update training.training_outbox set attempts = attempts + 1, last_error = :error "
                    "where id = :id"
                ),
                {"error": f"{type(error).__name__}: {error}"[:500], "id": row.id},
            )
            return {"published": published, "pending": len(rows) - published}
        await connection.execute(
            text(
                "update training.training_outbox set published_at = now(), attempts = attempts + 1, "
                "last_error = null where id = :id"
            ),
            {"id": row.id},
        )
        published += 1
    return {"published": published, "pending": len(rows) - published}


BACKFILLED: set = set()


RECORDS = fichas.Every()
METRICS = fichas.Every()


async def run_once(client: httpx.AsyncClient) -> dict[str, int]:
    total = {"published": 0, "pending": 0}
    for user in await users(client):
        with as_user(user):
            await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
            await cifras.refresh(engine, MODULE, metrics.build, METRICS, user)
            async with engine().begin() as connection:
                await connection.execute(text('set local role "mod_training"'))
                if user not in BACKFILLED:
                    await agenda.backfill(connection)
                    await agenda.backfill_activities(connection)
                    await links.backfill(connection)
                    await workouts.backfill(connection)
                    await activities.join_twins(connection)
                    BACKFILLED.add(user)
                await activities.receive(connection)
                await activities.receive_exercises(connection)
                await bodyweight.forward(connection, client)
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
                    print(f"publisher · {result['pending']} pendiente(s), reintento", flush=True)
                else:
                    failures = 0
                    if result["published"]:
                        print(f"publisher · {result['published']} publicado(s)", flush=True)
            except Exception as error:  # noqa: BLE001 - un fallo de base no tumba el proceso
                failures += 1
                print(f"publisher · {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            await asyncio.sleep(min(60.0, INTERVAL_SECONDS * (2 ** min(failures, 4))))


def main() -> int:
    print(f"publisher · training → {kernel_url()} cada {INTERVAL_SECONDS:g} s", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(loop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
