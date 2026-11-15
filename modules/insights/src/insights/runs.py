from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import ai
from insights import hub

MODULE = "insights"
PENDING_DAYS = 3
ENDED = {"done": "ok", "failed": "failed", "over_budget": "rate_limited"}
REFUSED = {403: "not_granted", 429: "rate_limited", 503: "no_account"}


def asked_as(key: str) -> str:
    return f"{MODULE}:{key}"


async def start(key: str, task: str, web: bool = False) -> dict[str, Any]:
    body = ai.RunRequest(role="smart", task=task, key=key, web=web).model_dump()
    try:
        answer = ai.RunResponse.model_validate(await hub.ask(ai.RUN, body))
    except hub.Refused as error:
        return {"outcome": "error", "code": REFUSED.get(error.status), "detail": str(error)}
    except hub.Unavailable as error:
        return {"outcome": "error", "detail": str(error)}
    if answer.status == "failed":
        return {"outcome": "error", "detail": answer.summary or "the run failed"}
    return {"outcome": "queued", "status": answer.status}


async def status(key: str) -> ai.StatusResponse | None:
    try:
        found = await hub.ask(ai.STATUS, ai.StatusRequest(key=key).model_dump())
    except hub.Unavailable:
        return None
    return ai.StatusResponse.model_validate(found)


PENDING = text("""
    select key from (
        select case when attempt > 1 then key || '#' || attempt else key end as key, asked_at
        from insights.insights_run where outcome = 'queued'
        union all
        select case when attempt > 1 then key || '#' || attempt else key end, asked_at
        from insights.insights_craft_run where outcome = 'queued'
        union all
        select 'thread:' || m.id::text, m.created_at
        from insights.insights_thread t
        join insights.insights_message m on m.thread_id = t.id and m.author = 'person'
        where t.waiting_since is not null and m.created_at >= t.waiting_since
    ) asked
    where asked_at > now() - make_interval(days => :days)
      and not exists (
          select 1 from insights.insights_ended e where e.key = 'insights:' || asked.key
      )
""")

NOTE = text("""
    insert into insights.insights_ended (key, outcome, detail, code, ran_with)
    values (:key, :outcome, :detail, :code, :ran_with)
    on conflict (user_id, key) do nothing
""")


async def note(connection: AsyncConnection, key: str, found: ai.StatusResponse) -> bool:
    outcome = ENDED.get(found.status)
    if outcome is None:
        return False
    ran_with = " · ".join(part for part in (found.provider, found.model) if part) or None
    await connection.execute(
        NOTE,
        {
            "key": asked_as(key),
            "outcome": outcome,
            "detail": (found.detail or found.summary or None),
            "code": outcome if outcome == "rate_limited" else None,
            "ran_with": ran_with[:120] if ran_with else None,
        },
    )
    return True


async def settle(connection: AsyncConnection) -> int:
    keys = [row.key for row in await connection.execute(PENDING, {"days": PENDING_DAYS})]
    ended = 0
    for key in keys:
        found = await status(key)
        if found is not None and await note(connection, key, found):
            ended += 1
    return ended
