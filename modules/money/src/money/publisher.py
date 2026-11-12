from __future__ import annotations

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import records as fichas
from arga_tenancy import USER_HEADER, current_user, kernel_url

MODULE = "money"
SOURCE = "app"
BATCH = 50

PENDING = text("""
    select id, type, ts, payload, dedup_hash, user_id
    from money.money_outbox
    where published_at is null
    order by id
    limit :batch
    for update skip locked
""")

FAILED = text("""
    update money.money_outbox
    set attempts = attempts + 1, last_error = :error where id = :id
""")

DONE = text("""
    update money.money_outbox
    set published_at = now(), attempts = attempts + 1, last_error = null where id = :id
""")


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
                FAILED, {"error": f"{type(error).__name__}: {error}"[:500], "id": row.id}
            )
            return {"published": published, "pending": len(rows) - published}
        await connection.execute(DONE, {"id": row.id})
        published += 1
    await fichas.prune(connection, "money")
    return {"published": published, "pending": len(rows) - published}
