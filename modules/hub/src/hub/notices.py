from __future__ import annotations

from datetime import time, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from hub.words import say

FAILING = "failing"
REAUTH = "reauth"
BLOCKED = "claude_blocked"
STREAK = 3
HOUR = time(9, 0)
HREF = "/hub"

CONNECTIONS = text("""
    select id, label, consent_expires_at from hub.hub_connection
    where not paused and status = 'active'
""")
RUNS = text("""
    select id, outcome, finished_at, detail from hub.hub_run
    where connection_id = :id and capability = 'sync' and outcome in ('ok', 'error')
    order by started_at desc
    limit :limit
""")


BLOCKED_RUNS = text("""
    select distinct on (app) id, app, finished_at, detail
    from (
        select id, split_part(idempotency_key, ':', 1) as app, finished_at, detail
        from hub.hub_run
        where capability = 'action' and operation = 'run' and code in ('no_room', 'no_account')
          and finished_at > now() - interval '1 day'
    ) as lost
    order by app, finished_at desc
""")
LATER_OK = text("""
    select 1 from hub.hub_run
    where capability = 'action' and operation = 'run' and outcome = 'ok'
      and split_part(idempotency_key, ':', 1) = :app and finished_at > :after
    limit 1
""")


async def blocked(connection: AsyncConnection) -> list[dict[str, Any]]:
    out = []
    for row in (await connection.execute(BLOCKED_RUNS)).all():
        if await connection.scalar(LATER_OK, {"app": row.app, "after": row.finished_at}):
            continue
        out.append(
            notify.notification(
                BLOCKED,
                f"claude_blocked:{row.id}",
                f"{row.app.capitalize()} could not use your Claude",
                HREF,
                row.finished_at,
                body=(row.detail or "None of your Claude accounts could do it.")[:400],
            )
        )
    return out


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = await blocked(connection)
    for row in (await connection.execute(CONNECTIONS)).all():
        runs = (await connection.execute(RUNS, {"id": row.id, "limit": STREAK})).all()
        if len(runs) == STREAK and all(one.outcome == "error" for one in runs):
            first = runs[-1]
            out.append(
                notify.notification(
                    FAILING,
                    f"failing:{row.id}:{first.id}",
                    say("notice.failing.title", label=row.label),
                    HREF,
                    runs[0].finished_at,
                    body=(runs[0].detail or say("notice.failing.body"))[:400],
                )
            )
        if row.consent_expires_at is not None:
            ends = row.consent_expires_at.date()
            for before in (7, 0):
                key = "notice.reauth.today" if before == 0 else "notice.reauth.days"
                out.append(
                    notify.notification(
                        REAUTH,
                        f"reauth:{row.id}:{ends.isoformat()}:{before}",
                        say(key, label=row.label, days=before),
                        HREF,
                        notify.at(ends - timedelta(days=before), HOUR),
                        body=say("notice.reauth.body"),
                    )
                )
    return out
