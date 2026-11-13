from __future__ import annotations

import json
import sys
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_agenda
from arga_tenancy import kernel_url, user_headers

MODULE = "planner"

LATEST = text(f"""
    select distinct on (payload->'{arga_agenda.KEY}'->>'uid')
        module, ts, ingested_at, payload->'{arga_agenda.KEY}' as item, payload->'layer' as layer
    from planner.events
    where module <> '{MODULE}' and payload ? '{arga_agenda.KEY}'
    order by payload->'{arga_agenda.KEY}'->>'uid', ingested_at desc, ts desc
""")

KNOWN = text("select uid, seen_at, layer from planner.planner_app_event")

UPSERT = text("""
    insert into planner.planner_app_event (app, uid, payload, version_ts, seen_at, layer)
    values (:app, :uid, cast(:payload as jsonb), :ts, :seen, :layer)
    on conflict (user_id, uid) do update
    set app = excluded.app, payload = excluded.payload, version_ts = excluded.version_ts,
        seen_at = excluded.seen_at, layer = excluded.layer, updated_at = now()
    where planner_app_event.seen_at is null or planner_app_event.seen_at < excluded.seen_at
       or planner_app_event.layer is distinct from excluded.layer
""")

LAYERS = text("select app, name from planner.planner_calendar where app is not null")

RENAME_LAYER = text(
    "update planner.planner_calendar set name = :name"
    " where app = :app and origin = 'app' and name = :old"
)

NEW_LAYER = text("""
    insert into planner.planner_calendar (name, tone, origin, app, position)
    values (:name, :tone, 'app', :app,
            coalesce((select max(position) + 1 from planner.planner_calendar
                      where origin = 'app'), 0))
    on conflict (user_id, app) where app is not null do nothing
""")

COUNT = text("select count(*) from planner.planner_calendar")


def kernel_transport() -> httpx.AsyncBaseTransport | None:
    return None


async def app_names() -> dict[str, str]:
    try:
        async with httpx.AsyncClient(transport=kernel_transport(), timeout=5.0) as client:
            response = await client.get(f"{kernel_url()}/modules", headers=user_headers())
        if response.status_code == 200:
            return {one["id"]: one["name"] for one in response.json()}
    except httpx.HTTPError:
        pass
    return {}


def _layer(value: Any) -> str | None:
    if isinstance(value, str) and 1 <= len(value.strip()) <= 40:
        return " ".join(value.split())
    return None


def layer_key(app: str, layer: str | None) -> str:
    return f"{app}:{layer}" if layer else app


def module_of(key: str) -> str:
    return key.split(":", 1)[0]


def _valid(item: Any) -> dict[str, Any] | None:
    try:
        return arga_agenda.validate(item)
    except arga_agenda.BadDated as error:
        uid = item.get("uid") if isinstance(item, dict) else None
        print(f"circle · dropped {uid}: {error}", file=sys.stderr, flush=True)
        return None


async def derive(connection: AsyncConnection) -> dict[str, int]:
    known = {row.uid: (row.seen_at, row.layer) for row in await connection.execute(KNOWN)}
    latest = []
    apps: set[str] = set()
    for row in await connection.execute(LATEST):
        item = _valid(row.item)
        if item is None:
            continue
        layer = _layer(row.layer)
        apps.add(layer_key(row.module, layer))
        latest.append((row, item, layer))

    existing = {row.app: row.name for row in await connection.execute(LAYERS)}
    missing = apps - set(existing)
    fallback = {
        key: name for key, name in existing.items() if ":" not in key and name == key.capitalize()
    }
    names = await app_names() if missing or fallback else {}
    for key, old in fallback.items():
        better = names.get(key)
        if better and better != old:
            await connection.execute(RENAME_LAYER, {"app": key, "name": better[:60], "old": old})

    changed = 0
    for row, item, layer in latest:
        seen, kept_layer = known.get(item["uid"], (None, None))
        if seen is not None and seen >= row.ingested_at and kept_layer == layer:
            continue
        await connection.execute(
            UPSERT,
            {
                "app": row.module,
                "uid": item["uid"],
                "payload": json.dumps(item),
                "ts": row.ts,
                "seen": row.ingested_at if seen is None or seen < row.ingested_at else seen,
                "layer": layer,
            },
        )
        changed += 1

    for key in sorted(missing):
        count = int(await connection.scalar(COUNT) or 0)
        app = module_of(key)
        name = names.get(app, app.capitalize())
        if key != app:
            name = f"{name} · {key.split(':', 1)[1]}"
        await connection.execute(NEW_LAYER, {"app": key, "name": name[:60], "tone": count % 10 + 1})
    return {"changed": changed, "layers": len(missing)}


IN_WINDOW = text("""
    select a.id::text as id, a.app, a.payload, c.id::text as calendar_id
    from planner.planner_app_event a
    join planner.planner_calendar c on c.app = coalesce(a.app || ':' || a.layer, a.app)
    where a.payload->>'status' <> 'cancelled'
      and (c.id = any(cast(:calendars as uuid[])) or cardinality(cast(:calendars as uuid[])) = 0)
      and case when (a.payload->>'all_day')::boolean
          then (a.payload->>'start')::date <= :last_day and (a.payload->>'end')::date >= :first_day
          else (a.payload->>'start')::timestamptz < :end
               and (a.payload->>'end')::timestamptz >= :start
      end
""")

MATCHING = text("""
    select a.id::text as id, a.app, a.payload, c.id::text as calendar_id
    from planner.planner_app_event a
    join planner.planner_calendar c on c.app = coalesce(a.app || ':' || a.layer, a.app)
    where a.payload->>'status' <> 'cancelled'
      and (a.payload->>'title' ilike :p or a.payload->>'location' ilike :p)
    order by (a.payload->>'start') desc
    limit 200
""")


@dataclass(frozen=True)
class AppRow:
    id: str
    app: str
    payload: dict[str, Any]
    calendar_id: str


async def in_window(
    connection: AsyncConnection, start: datetime, end: datetime, calendar_ids: list[str]
) -> list[AppRow]:
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
    return [AppRow(**row._mapping) for row in rows]


BY_ID = text("""
    select a.id::text as id, a.app, a.payload, c.id::text as calendar_id
    from planner.planner_app_event a
    join planner.planner_calendar c on c.app = coalesce(a.app || ':' || a.layer, a.app)
    where a.id = cast(:id as uuid)
""")


async def by_id(connection: AsyncConnection, app_event_id: str) -> AppRow:
    row = (await connection.execute(BY_ID, {"id": app_event_id})).one_or_none()
    if row is None:
        raise NotFound(app_event_id)
    return AppRow(**row._mapping)


async def matching(connection: AsyncConnection, pattern: str) -> list[AppRow]:
    return [AppRow(**row._mapping) for row in await connection.execute(MATCHING, {"p": pattern})]


MOVE = "agenda.move"

ONE = text("""
    select a.app, a.uid from planner.planner_app_event a where a.id = cast(:id as uuid)
""")

MOVED = text("""
    update planner.planner_app_event
    set payload = cast(:payload as jsonb), seen_at = now(), updated_at = now()
    where id = cast(:id as uuid)
""")


class NotFound(Exception):
    pass


class Refused(Exception):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


async def movable() -> set[str]:
    try:
        async with httpx.AsyncClient(transport=kernel_transport(), timeout=5.0) as client:
            response = await client.get(f"{kernel_url()}/modules", headers=user_headers())
        if response.status_code == 200:
            return {one["id"] for one in response.json() if MOVE in one.get("provides", [])}
    except httpx.HTTPError:
        pass
    return set()


async def move(
    transaction: Callable[[], AbstractAsyncContextManager[AsyncConnection]],
    app_event_id: str,
    start: str,
    end: str,
    all_day: bool,
) -> dict[str, Any]:
    async with transaction() as connection:
        try:
            row = (await connection.execute(ONE, {"id": app_event_id})).one_or_none()
        except Exception as error:  # noqa: BLE001 -- an id that is not a uuid is an id that is not there
            raise NotFound(app_event_id) from error
    if row is None:
        raise NotFound(app_event_id)
    try:
        async with httpx.AsyncClient(transport=kernel_transport(), timeout=30.0) as client:
            response = await client.post(
                f"{kernel_url()}/internal/capabilities/{MOVE}",
                json={"uid": row.uid, "start": start, "end": end, "all_day": all_day},
                headers={**user_headers(), "x-arga-module": MODULE, "x-arga-target": row.app},
            )
    except httpx.HTTPError as error:
        raise Refused(f"{row.app} no contesta ({type(error).__name__})", 503) from error
    try:
        detail = response.json().get("detail") if response.status_code != 200 else None
    except ValueError:
        detail = None
    if response.status_code in (404, 409, 422) and isinstance(detail, str):
        raise Refused(detail, 409)
    if response.status_code != 200:
        raise Refused(
            detail if isinstance(detail, str) else f"{row.app} contesta {response.status_code}"
        )
    item = _valid(response.json().get(arga_agenda.KEY))
    if item is None or item["uid"] != row.uid:
        raise Refused(f"{row.app} answers something that does not fit")
    async with transaction() as connection:
        await connection.execute(MOVED, {"id": app_event_id, "payload": json.dumps(item)})
    return item
