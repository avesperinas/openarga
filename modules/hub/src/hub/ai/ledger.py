from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hub.ai.providers import Usage

SPENT = text("""
    select coalesce(sum(input_tokens + output_tokens), 0)
    from hub.ai_attempt
    where started_at >= date_trunc('month', now())
""")

OPEN = text("""
    insert into hub.ai_attempt (app, capability, role, provider, model, run_key, status)
    values (:app, :capability, :role, :provider, :model, :run_key, :status)
    returning id
""")

CLOSE = text("""
    update hub.ai_attempt
    set status = :status, steps = :steps, input_tokens = :input_tokens,
        output_tokens = :output_tokens, detail = :detail, summary = :summary,
        finished_at = now()
    where id = :id
""")

RECENT = text("""
    select id, app, capability, role, provider, model, run_key, status, steps,
           input_tokens, output_tokens, detail, summary, started_at, finished_at
    from hub.ai_attempt
    order by started_at desc
    limit :limit
""")


class Attempt(BaseModel):
    id: UUID
    app: str
    capability: str
    role: str
    provider: str
    model: str
    run_key: str | None
    status: str
    steps: int
    input_tokens: int
    output_tokens: int
    detail: str | None
    summary: str | None
    started_at: datetime
    finished_at: datetime | None


async def spent(connection: AsyncConnection) -> int:
    return int(await connection.scalar(SPENT) or 0)


async def left(connection: AsyncConnection, monthly: int | None) -> int | None:
    return None if monthly is None else max(0, monthly - await spent(connection))


async def open_attempt(
    connection: AsyncConnection,
    *,
    app: str,
    capability: str,
    role: str,
    provider: str,
    model: str,
    run_key: str | None = None,
    status: str = "running",
) -> UUID:
    return await connection.scalar(
        OPEN,
        {
            "app": app,
            "capability": capability,
            "role": role,
            "provider": provider,
            "model": model,
            "run_key": run_key,
            "status": status,
        },
    )


async def close_attempt(
    connection: AsyncConnection,
    attempt: UUID,
    status: str,
    usage: Usage,
    *,
    steps: int = 1,
    detail: str | None = None,
    summary: str | None = None,
) -> None:
    await connection.execute(
        CLOSE,
        {
            "id": attempt,
            "status": status,
            "steps": steps,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "detail": detail[:2000] if detail else None,
            "summary": summary[:4000] if summary else None,
        },
    )


async def recent(connection: AsyncConnection, limit: int = 50) -> list[Attempt]:
    rows = (await connection.execute(RECENT, {"limit": limit})).mappings().all()
    return [Attempt(**row) for row in rows]
