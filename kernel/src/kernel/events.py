from __future__ import annotations

import hashlib
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import text

from arga_tenancy import require_person
from kernel.db import engine
from kernel.entities import EntityRef, resolve_alias
from kernel.provision import MODULE_ID_PATTERN

router = APIRouter(tags=["events"])

SOURCE_PATTERN = r"^[a-z][a-z0-9_-]{1,63}$"
TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_BATCH = 500

COLUMNS = "id, ts, ingested_at, module, source, type, entity_id, payload, dedup_hash"

INSERT_EVENT = text("""
    insert into kernel.events (ts, module, source, type, entity_id, payload, dedup_hash)
    values (
        :ts, :module, :source, :type,
        cast(:entity_id as uuid), cast(:payload as jsonb), :dedup_hash
    )
    on conflict (user_id, dedup_hash) do nothing
    returning id
""")

FIND_BY_DEDUP_HASH = text(
    "select id, cast(entity_id as text) as entity_id "
    "from kernel.events where dedup_hash = :dedup_hash "
    "and user_id = nullif(current_setting('arga.user_id', true), '')::uuid"
)

ENQUEUE = text("""
    insert into kernel.resolution_queue (event_id, raw_alias, source)
    values (cast(:event_id as uuid), :raw_alias, :source)
""")


class EventIn(BaseModel):
    ts: AwareDatetime
    module: Annotated[str, Field(pattern=MODULE_ID_PATTERN)]
    source: Annotated[str, Field(pattern=SOURCE_PATTERN)]
    type: Annotated[str, Field(pattern=TYPE_PATTERN)]
    entity_id: UUID | None = None
    entity: EntityRef | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    dedup_hash: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class Event(BaseModel):
    id: UUID
    ts: datetime
    ingested_at: datetime
    module: str
    source: str
    type: str
    entity_id: UUID | None
    payload: dict[str, Any]
    dedup_hash: str


class Ingested(BaseModel):
    id: UUID
    dedup_hash: str
    created: bool
    entity_id: UUID | None = None
    queued: bool = False


class EventPage(BaseModel):
    events: list[Event]
    next_cursor: str | None


def derive_dedup_hash(event: EventIn) -> str:
    identity = json.dumps(
        {
            "module": event.module,
            "source": event.source,
            "type": event.type,
            "ts": event.ts.astimezone(UTC).isoformat(),
            "payload": event.payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"auto:{hashlib.sha256(identity.encode()).hexdigest()}"


def encode_cursor(ts: datetime, event_id: UUID) -> str:
    return urlsafe_b64encode(f"{ts.isoformat()}|{event_id}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, _, event_id = raw.partition("|")
        return datetime.fromisoformat(ts), UUID(event_id)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=422, detail="invalid cursor") from error


def check_entity(event: EventIn) -> None:
    if event.entity_id is not None and event.entity is not None:
        raise HTTPException(
            status_code=422,
            detail="send entity_id when you already know the entity, or entity to resolve it",
        )


async def ingest_one(connection, event: EventIn) -> Ingested:
    dedup_hash = event.dedup_hash or derive_dedup_hash(event)
    resolution = None
    if event.entity is not None:
        resolution = await resolve_alias(connection, event.module, event.source, event.entity)

    entity_id = event.entity_id if resolution is None else resolution.entity_id
    inserted = await connection.scalar(
        INSERT_EVENT,
        {
            "ts": event.ts,
            "module": event.module,
            "source": event.source,
            "type": event.type,
            "entity_id": str(entity_id) if entity_id else None,
            "payload": json.dumps(event.payload),
            "dedup_hash": dedup_hash,
        },
    )

    if inserted is None:
        existing = (await connection.execute(FIND_BY_DEDUP_HASH, {"dedup_hash": dedup_hash})).one()
        return Ingested(
            id=existing.id, dedup_hash=dedup_hash, created=False, entity_id=existing.entity_id
        )

    queued = resolution is not None and resolution.created
    if queued:
        await connection.execute(
            ENQUEUE,
            {"event_id": str(inserted), "raw_alias": event.entity.alias, "source": event.source},
        )
    return Ingested(
        id=inserted, dedup_hash=dedup_hash, created=True, entity_id=entity_id, queued=queued
    )


@router.post("/events")
async def ingest(event: EventIn) -> Ingested:
    require_person()
    check_entity(event)
    async with engine().begin() as connection:
        return await ingest_one(connection, event)


class Batch(BaseModel):
    events: Annotated[list[EventIn], Field(min_length=1, max_length=MAX_BATCH)]


class BatchIngested(BaseModel):
    results: list[Ingested]


@router.post("/events/batch")
async def ingest_batch(batch: Batch) -> BatchIngested:
    require_person()
    for event in batch.events:
        check_entity(event)
    async with engine().begin() as connection:
        return BatchIngested(results=[await ingest_one(connection, one) for one in batch.events])


@router.get("/events")
async def list_events(
    module: Annotated[str | None, Query(pattern=MODULE_ID_PATTERN)] = None,
    type: Annotated[str | None, Query(pattern=TYPE_PATTERN)] = None,
    entity_id: UUID | None = None,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> EventPage:
    conditions: list[str] = []
    parameters: dict[str, Any] = {"limit": limit + 1}

    if module is not None:
        conditions.append("module = :module")
        parameters["module"] = module
    if type is not None:
        conditions.append("type = :type")
        parameters["type"] = type
    if entity_id is not None:
        conditions.append("entity_id in (select kernel.entity_family(cast(:entity_id as uuid)))")
        parameters["entity_id"] = str(entity_id)
    if since is not None:
        conditions.append("ts >= :since")
        parameters["since"] = since
    if until is not None:
        conditions.append("ts < :until")
        parameters["until"] = until
    if cursor is not None:
        cursor_ts, cursor_id = decode_cursor(cursor)
        conditions.append("(ts, id) < (cast(:cursor_ts as timestamptz), cast(:cursor_id as uuid))")
        parameters["cursor_ts"] = cursor_ts
        parameters["cursor_id"] = str(cursor_id)

    where = " and ".join(conditions) if conditions else "true"
    listing = text(
        f"select {COLUMNS} from kernel.events where {where} order by ts desc, id desc limit :limit"
    )

    async with engine().connect() as connection:
        rows = (await connection.execute(listing, parameters)).all()

    next_cursor = (
        encode_cursor(rows[limit - 1].ts, rows[limit - 1].id) if len(rows) > limit else None
    )
    events = [
        Event(
            id=row.id,
            ts=row.ts,
            ingested_at=row.ingested_at,
            module=row.module,
            source=row.source,
            type=row.type,
            entity_id=row.entity_id,
            payload=row.payload if isinstance(row.payload, dict) else json.loads(row.payload),
            dedup_hash=row.dedup_hash,
        )
        for row in rows[:limit]
    ]

    return EventPage(events=events, next_cursor=next_cursor)
