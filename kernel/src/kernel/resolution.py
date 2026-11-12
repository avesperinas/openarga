from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import require_person
from kernel import resolver
from kernel.db import engine
from kernel.entities import (
    RESOLVE_FAMILY,
    Entity,
    Suggestion,
    in_family,
    merge_entities,
    read_entity,
    suggest,
    surviving,
)

router = APIRouter(tags=["resolution"])

MAX_PENDING = 200

PENDING = text("""
    select q.id, q.event_id, q.raw_alias, q.source, q.created_at, q.resolved_at,
           cast(c.id as text) as candidate_id, c.name as candidate_name,
           c.kind as candidate_kind, c.module as candidate_module, c.status as candidate_status
    from kernel.resolution_queue q
    join kernel.events e on e.id = q.event_id
    join kernel.entities c on c.id = e.entity_id
    where (
        cast(:resolved as boolean) is null
        or (q.resolved_at is not null) = cast(:resolved as boolean)
      )
    order by q.created_at, q.id
    limit :limit
""")

READ_ITEM = text("""
    select q.id, q.resolved_at, cast(e.entity_id as text) as candidate_id
    from kernel.resolution_queue q
    join kernel.events e on e.id = q.event_id
    where q.id = cast(:item_id as uuid)
""")

CONFIRM_ENTITY = text("""
    update kernel.entities
    set status = 'confirmed', updated_at = now()
    where id = cast(:entity_id as uuid) and status = 'candidate'
""")


class Candidate(BaseModel):
    id: UUID
    name: str
    kind: str
    module: str
    status: str


class QueueItem(BaseModel):
    id: UUID
    event_id: UUID
    raw_alias: str
    source: str
    created_at: datetime
    resolved_at: datetime | None
    candidate: Candidate
    suggestions: list[Suggestion]


class MergeRequest(BaseModel):
    into: UUID


async def _load_item(connection: AsyncConnection, item_id: UUID):
    row = (await connection.execute(READ_ITEM, {"item_id": str(item_id)})).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"queue item '{item_id}' does not exist")
    if row.resolved_at is not None:
        raise HTTPException(
            status_code=409,
            detail=f"queue item '{item_id}' was already resolved at {row.resolved_at}",
        )
    return row


@router.get("/resolution-queue")
async def list_queue(
    resolved: bool | None = False,
    limit: Annotated[int, Query(ge=1, le=MAX_PENDING)] = 50,
) -> list[QueueItem]:
    async with engine().connect() as connection:
        rows = (await connection.execute(PENDING, {"resolved": resolved, "limit": limit})).all()
        items = []
        for row in rows:
            items.append(
                QueueItem(
                    id=row.id,
                    event_id=row.event_id,
                    raw_alias=row.raw_alias,
                    source=row.source,
                    created_at=row.created_at,
                    resolved_at=row.resolved_at,
                    candidate=Candidate(
                        id=row.candidate_id,
                        name=row.candidate_name,
                        kind=row.candidate_kind,
                        module=row.candidate_module,
                        status=row.candidate_status,
                    ),
                    suggestions=await suggest(
                        connection,
                        module=row.candidate_module,
                        kind=row.candidate_kind,
                        alias=row.raw_alias,
                        exclude=row.candidate_id,
                    ),
                )
            )
    return items


@router.post("/resolution-queue/{item_id}/confirm")
async def confirm(item_id: UUID) -> Entity:
    require_person()
    async with engine().begin() as connection:
        item = await _load_item(connection, item_id)
        await connection.execute(CONFIRM_ENTITY, {"entity_id": item.candidate_id})
        await connection.execute(RESOLVE_FAMILY, {"entity_id": item.candidate_id})
        entity = await read_entity(connection, UUID(item.candidate_id))
    return entity


@router.post("/resolution-queue/{item_id}/merge")
async def merge(item_id: UUID, request: MergeRequest) -> Entity:
    require_person()
    async with engine().begin() as connection:
        item = await _load_item(connection, item_id)

        target = await surviving(connection, request.into)
        if target is None:
            raise HTTPException(status_code=404, detail=f"entity '{request.into}' does not exist")
        if target == item.candidate_id:
            raise HTTPException(status_code=422, detail="an entity cannot be merged into itself")
        if await in_family(connection, target, item.candidate_id):
            raise HTTPException(
                status_code=422,
                detail=f"entity '{target}' is already part of '{item.candidate_id}'",
            )

        candidate = await read_entity(connection, UUID(item.candidate_id))
        survivor = await read_entity(connection, UUID(target))
        if (candidate.module, candidate.kind) != (survivor.module, survivor.kind):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"cannot merge {candidate.module}/{candidate.kind} into "
                    f"{survivor.module}/{survivor.kind}"
                ),
            )

        await merge_entities(
            connection,
            item.candidate_id,
            target,
            method="manual",
            decided_by="person",
            confidence=1.0,
            evidence=f"fusión pedida desde la cola, item {item_id}",
        )
        await connection.execute(CONFIRM_ENTITY, {"entity_id": target})
        entity = await read_entity(connection, UUID(target))
    return entity


class PassSummary(BaseModel):
    examined: int
    merged: list[dict]
    abstained: list[dict]
    threshold: float


@router.post("/resolution/run")
async def run_resolver() -> PassSummary:
    async with engine().begin() as connection:
        outcome = await resolver.run(connection)

    return PassSummary(
        examined=outcome.examined,
        merged=[
            {
                "candidate": decision.candidate_name,
                "into": decision.target_name,
                "rule": decision.rule,
                "confidence": decision.confidence,
                "evidence": decision.evidence,
            }
            for decision in outcome.merged
        ],
        abstained=[
            {
                "entity": skipped.name,
                "closest": skipped.best_name,
                "confidence": skipped.best_confidence,
                "reason": skipped.reason,
            }
            for skipped in outcome.abstained
        ],
        threshold=resolver.AUTO_MERGE_CONFIDENCE,
    )
