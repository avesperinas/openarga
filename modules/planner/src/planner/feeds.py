from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

EVENT = "calendar.event"
FEED = "calendar.feed"
RUN = "hub.run"
CONNECTION = "hub.connection"
INLET = "planner.calendar"

LATEST_FEEDS = text("""
    select distinct on (payload->>'connection')
        payload->>'connection' as connection, payload
    from planner.events
    where type = 'calendar.feed'
    order by payload->>'connection', ts desc, ingested_at desc
""")

VERSIONS = text("""
    select distinct on (payload->>'uid', payload->>'fingerprint') payload
    from planner.events
    where type = 'calendar.event' and payload->>'connection' = :connection
    order by payload->>'uid', payload->>'fingerprint', ts desc, ingested_at desc
""")

KNOWN = text("""
    select uid, fingerprint, removed from planner.planner_feed_event
    where connection_id = cast(:connection as uuid)
""")

UPSERT = text("""
    insert into planner.planner_feed_event (connection_id, uid, fingerprint, payload)
    values (cast(:connection as uuid), :uid, :fingerprint, cast(:payload as jsonb))
    on conflict (user_id, connection_id, uid) do update
    set fingerprint = excluded.fingerprint, payload = excluded.payload, removed = false,
        updated_at = now()
""")

REMOVE = text("""
    update planner.planner_feed_event set removed = true, updated_at = now()
    where connection_id = cast(:connection as uuid) and not removed
      and not (uid = any(cast(:uids as text[])))
""")

LAYER_OF = text("""
    select 1 from planner.planner_calendar where connection_id = cast(:connection as uuid)
""")

NEW_LAYER = text("""
    insert into planner.planner_calendar (name, tone, origin, connection_id, position)
    values (:name, :tone, 'subscription', cast(:connection as uuid),
            coalesce((select max(position) + 1 from planner.planner_calendar
                      where origin = 'subscription'), 0))
    on conflict (user_id, connection_id) where connection_id is not null do nothing
""")

LAYERS = text("select count(*) from planner.planner_calendar")


async def add_layer(connection: AsyncConnection, connection_id: str, name: str, tone: int) -> str:
    await connection.execute(
        NEW_LAYER, {"connection": connection_id, "name": name[:60], "tone": tone}
    )
    await connection.execute(
        text(
            "update planner.planner_calendar set name = :name, tone = :tone "
            "where connection_id = cast(:connection as uuid)"
        ),
        {"connection": connection_id, "name": name[:60], "tone": tone},
    )
    return await connection.scalar(
        text(
            "select id::text from planner.planner_calendar "
            "where connection_id = cast(:connection as uuid)"
        ),
        {"connection": connection_id},
    )


async def derive(connection: AsyncConnection) -> dict[str, int]:
    changed = removed = layers = 0
    known_states = await statuses(connection)
    gone = {key for key, status in known_states.items() if status.removed}
    for key in gone:
        result = await connection.execute(REMOVE, {"connection": key, "uids": []})
        removed += result.rowcount or 0
    feeds = (await connection.execute(LATEST_FEEDS)).all()
    for feed in feeds:
        if feed.connection in gone:
            continue
        wanted: dict[str, str] = feed.payload.get("events") or {}
        versions = {
            (row.payload["uid"], row.payload["fingerprint"]): row.payload
            for row in await connection.execute(VERSIONS, {"connection": feed.connection})
        }
        known = {
            row.uid: (row.fingerprint, row.removed)
            for row in await connection.execute(KNOWN, {"connection": feed.connection})
        }
        for uid, fingerprint in wanted.items():
            payload = versions.get((uid, fingerprint))
            if payload is None or known.get(uid) == (fingerprint, False):
                continue
            await connection.execute(
                UPSERT,
                {
                    "connection": feed.connection,
                    "uid": uid,
                    "fingerprint": fingerprint,
                    "payload": json.dumps(payload),
                },
            )
            changed += 1
        result = await connection.execute(
            REMOVE, {"connection": feed.connection, "uids": list(wanted)}
        )
        removed += result.rowcount or 0
        if not await connection.scalar(LAYER_OF, {"connection": feed.connection}):
            state = known_states.get(feed.connection)
            plugged = state.plug if state else {}
            count = int(await connection.scalar(LAYERS) or 0)
            tone = plugged.get("tone")
            await connection.execute(
                NEW_LAYER,
                {
                    "connection": feed.connection,
                    "name": str(plugged.get("name") or feed.payload.get("label") or "Suscripción")[
                        :60
                    ],
                    "tone": tone if isinstance(tone, int) and 1 <= tone <= 10 else count % 10 + 1,
                },
            )
            layers += 1
    return {"changed": changed, "removed": removed, "layers": layers}


@dataclass(frozen=True)
class Status:
    provider: str | None
    updated_at: datetime | None
    failing: bool
    detail: str | None
    removed: bool
    paused: bool
    plug: dict[str, Any] = field(default_factory=dict)


LAST_RUNS = text("""
    select distinct on (payload->>'connection')
        payload->>'connection' as connection, payload
    from planner.events
    where type = 'hub.run'
    order by payload->>'connection', ts desc, ingested_at desc
""")

LAST_OK = text("""
    select payload->>'connection' as connection, max(ts) as at
    from planner.events
    where type = 'hub.run' and payload->>'outcome' = 'ok'
    group by 1
""")

LAST_STATE = text("""
    select distinct on (payload->>'connection')
        payload->>'connection' as connection, payload
    from planner.events
    where type = 'hub.connection'
    order by payload->>'connection', ts desc, ingested_at desc
""")


async def removed(connection: AsyncConnection) -> set[str]:
    return {
        row.connection
        for row in await connection.execute(LAST_STATE)
        if (row.payload or {}).get("removed")
    }


async def statuses(connection: AsyncConnection) -> dict[str, Status]:
    runs = {row.connection: row.payload for row in await connection.execute(LAST_RUNS)}
    ok = {row.connection: row.at for row in await connection.execute(LAST_OK)}
    states = {row.connection: row.payload for row in await connection.execute(LAST_STATE)}
    out: dict[str, Status] = {}
    for key in set(runs) | set(states):
        run = runs.get(key) or {}
        state = states.get(key) or {}
        failing = run.get("outcome") in ("error", "rate_limited")
        out[key] = Status(
            provider=run.get("provider") or state.get("provider"),
            updated_at=ok.get(key),
            failing=failing,
            detail=run.get("detail") if failing else None,
            removed=bool(state.get("removed")),
            paused=bool(state.get("paused")) and not state.get("removed"),
            plug=(state.get("plugs") or {}).get(INLET) or {},
        )
    return out


IN_WINDOW = text("""
    select f.id::text as id, f.connection_id::text as connection_id, f.uid, f.payload,
           c.id::text as calendar_id
    from planner.planner_feed_event f
    join planner.planner_calendar c on c.connection_id = f.connection_id
    where not f.removed
      and coalesce(f.payload->>'status', 'confirmed') <> 'cancelled'
      and (c.id = any(cast(:calendars as uuid[])) or cardinality(cast(:calendars as uuid[])) = 0)
      and case when (f.payload->>'all_day')::boolean
          then (f.payload->>'start')::date <= :last_day and (f.payload->>'end')::date >= :first_day
          else (f.payload->>'start')::timestamptz < :end
               and (f.payload->>'end')::timestamptz >= :start
      end
      and not exists (
          select 1 from planner.planner_feed_hidden h
          where h.connection_id = f.connection_id and h.uid = f.uid
      )
""")

MATCHING = text("""
    select f.id::text as id, f.connection_id::text as connection_id, f.uid, f.payload,
           c.id::text as calendar_id
    from planner.planner_feed_event f
    join planner.planner_calendar c on c.connection_id = f.connection_id
    where not f.removed
      and coalesce(f.payload->>'status', 'confirmed') <> 'cancelled'
      and (f.payload->>'title' ilike :p or f.payload->>'location' ilike :p
           or f.payload->>'description' ilike :p)
      and not exists (
          select 1 from planner.planner_feed_hidden h
          where h.connection_id = f.connection_id and h.uid = f.uid
      )
    order by (f.payload->>'start') desc
    limit 200
""")


@dataclass(frozen=True)
class FeedRow:
    id: str
    connection_id: str
    uid: str
    payload: dict[str, Any]
    calendar_id: str


async def in_window(
    connection: AsyncConnection, start: datetime, end: datetime, calendar_ids: list[str]
) -> list[FeedRow]:
    rows = await connection.execute(
        IN_WINDOW,
        {
            "start": start,
            "end": end,
            "first_day": start.date() - timedelta(days=1),
            "last_day": end.date() + timedelta(days=1),
            "calendars": calendar_ids,
        },
    )
    return [FeedRow(**row._mapping) for row in rows]


async def matching(connection: AsyncConnection, pattern: str) -> list[FeedRow]:
    return [FeedRow(**row._mapping) for row in await connection.execute(MATCHING, {"p": pattern})]


FIND = text("""
    select connection_id::text as connection_id, uid, payload
    from planner.planner_feed_event where id = cast(:id as uuid)
""")

HIDE = text("""
    insert into planner.planner_feed_hidden (connection_id, uid, original_start)
    values (cast(:connection as uuid), :uid, :start)
    on conflict do nothing
""")


class NotFound(LookupError):
    pass


async def hide(connection: AsyncConnection, feed_id: str) -> None:
    row = (await connection.execute(FIND, {"id": feed_id})).one_or_none()
    if row is None:
        raise NotFound(f"lo suscrito {feed_id}")
    raw = row.payload["start"]
    start = (
        datetime.combine(date.fromisoformat(raw), datetime.min.time())
        if row.payload.get("all_day")
        else datetime.fromisoformat(raw).replace(tzinfo=None)
    )
    await connection.execute(
        HIDE, {"connection": row.connection_id, "uid": row.uid, "start": start}
    )
