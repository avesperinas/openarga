from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import require_person
from kernel.db import engine
from kernel.identity import AUTO_MERGE_CONFIDENCE, Match, compare

router = APIRouter(tags=["entities"])

KIND_PATTERN = r"^[a-z][a-z0-9_]{1,30}$"

SIMILARITY_FLOOR = 0.3
MAX_SUGGESTIONS = 5

FIND_ALIAS = text("""
    select kernel.surviving_entity(entity_id) as entity_id
    from kernel.entity_aliases
    where source = :source and alias = :alias
""")

CREATE_CANDIDATE = text("""
    insert into kernel.entities (kind, module, name, status)
    values (:kind, :module, :name, 'candidate')
    returning id
""")

REGISTER_ALIAS = text("""
    insert into kernel.entity_aliases (entity_id, alias, source, confidence)
    values (cast(:entity_id as uuid), :alias, :source, :confidence)
""")

FAMILY_ALIASES = text("""
    select a.alias, a.source, a.confidence, cast(a.entity_id as text) as entity_id,
           d.method, d.rule, d.confidence as decision_confidence, d.evidence,
           d.decided_by, d.decided_at
    from kernel.entity_aliases a
    left join lateral (
        select method, rule, confidence, evidence, decided_by, decided_at
        from kernel.entity_decisions
        where loser_id = a.entity_id and decision = 'merged'
        order by decided_at desc, id desc
        limit 1
    ) d on true
    where a.entity_id in (select kernel.entity_family(cast(:entity_id as uuid)))
    order by a.source, a.alias
""")

DECISIONS = text("""
    select cast(d.id as text) as id,
           cast(d.loser_id as text) as loser_id, loser.name as loser_name,
           cast(d.winner_id as text) as winner_id, winner.name as winner_name,
           d.decision, d.method, d.rule, d.confidence, d.evidence, d.decided_by, d.decided_at
    from kernel.entity_decisions d
    join kernel.entities loser on loser.id = d.loser_id
    join kernel.entities winner on winner.id = d.winner_id
    where cast(:entity_id as uuid) is null
       or d.loser_id = cast(:entity_id as uuid)
       or d.winner_id = cast(:entity_id as uuid)
    order by d.decided_at desc, d.id desc
    limit :limit
""")

READ_ENTITY = text("""
    select cast(id as text) as id, kind, module, name, status,
           cast(merged_into as text) as merged_into
    from kernel.entities
    where id = cast(:entity_id as uuid)
""")

MERGED_INTO_THIS = text("""
    select cast(id as text) as id
    from kernel.entities
    where id in (select kernel.entity_family(cast(:entity_id as uuid)))
      and id <> cast(:entity_id as uuid)
    order by created_at
""")

SUGGESTIONS = text("""
    select cast(id as text) as id, name, kind,
           round(cast(similarity(name, :alias) as numeric), 3) as score
    from kernel.entities
    where module = :module
      and kind = :kind
      and status <> 'merged'
      and id <> cast(:exclude as uuid)
      and similarity(name, :alias) >= :floor
    order by similarity(name, :alias) desc, name
    limit :limit
""")


FAMILY_ALIAS_ARRAY = """
    coalesce(
        (select array_agg(a.alias)
         from kernel.entity_aliases a
         where a.entity_id in (select kernel.entity_family(e.id))),
        '{}'
    ) as aliases
"""

MATCH_CANDIDATES = text(f"""
    select cast(e.id as text) as id, e.name, e.status, {FAMILY_ALIAS_ARRAY}
    from kernel.entities e
    where e.module = :module
      and e.kind = :kind
      and e.status <> 'merged'
      and e.id <> cast(:entity_id as uuid)
""")

SUBJECT = text(f"""
    select e.name, e.module, e.kind, {FAMILY_ALIAS_ARRAY}
    from kernel.entities e
    where e.id = cast(:entity_id as uuid)
""")


MERGE_ENTITY = text("""
    update kernel.entities
    set status = 'merged', merged_into = cast(:target as uuid), updated_at = now()
    where id = cast(:candidate as uuid)
""")

RESOLVE_FAMILY = text("""
    update kernel.resolution_queue q
    set resolved_at = now()
    from kernel.events e
    where q.event_id = e.id
      and q.resolved_at is null
      and e.entity_id in (select kernel.entity_family(cast(:entity_id as uuid)))
""")

SURVIVOR = text("select cast(kernel.surviving_entity(cast(:entity_id as uuid)) as text)")

RECORD_DECISION = text("""
    insert into kernel.entity_decisions
        (loser_id, winner_id, decision, method, rule, confidence, evidence, decided_by)
    values (cast(:loser as uuid), cast(:winner as uuid), :decision, :method, :rule,
            cast(:confidence as double precision), :evidence, :decided_by)
""")

LAST_WORD = text("""
    select decision
    from kernel.entity_decisions
    where pair_key = least(cast(:left as uuid), cast(:right as uuid))::text || ':' ||
                     greatest(cast(:left as uuid), cast(:right as uuid))::text
    order by decided_at desc, id desc
    limit 1
""")

MERGED_VIA = text("""
    select method, rule, confidence, evidence, decided_by, decided_at
    from kernel.entity_decisions
    where loser_id = cast(:entity_id as uuid) and decision = 'merged'
    order by decided_at desc, id desc
    limit 1
""")

DETACH = text("""
    update kernel.entities
    set status = 'candidate', merged_into = null, updated_at = now()
    where id = cast(:entity_id as uuid) and status = 'merged'
""")

IN_FAMILY = text("""
    select exists (
        select 1
        where cast(:target as uuid) in (select kernel.entity_family(cast(:candidate as uuid)))
    )
""")


class EntityRef(BaseModel):
    alias: Annotated[str, Field(min_length=1, max_length=500)]
    kind: Annotated[str, Field(pattern=KIND_PATTERN)]


class Provenance(BaseModel):
    method: str
    rule: str | None
    confidence: float | None
    evidence: str | None
    decided_by: str
    decided_at: datetime


class Alias(BaseModel):
    alias: str
    source: str
    confidence: float
    entity_id: UUID
    via: Provenance | None = None


class Suggestion(BaseModel):
    id: UUID
    name: str
    kind: str
    score: float


class Entity(BaseModel):
    id: UUID
    kind: str
    module: str
    name: str
    status: str
    merged_into: UUID | None
    aliases: list[Alias]
    merged: list[UUID]
    merged_via: Provenance | None = None


class MatchCandidate(BaseModel):
    entity_id: UUID
    name: str
    status: str
    rule: str
    confidence: float
    evidence: str
    matched: tuple[str, str]
    would_merge: bool


class Matches(BaseModel):
    entity_id: UUID
    name: str
    threshold: float
    candidates: list[MatchCandidate]


class Resolution(BaseModel):
    entity_id: UUID
    created: bool


async def resolve_alias(
    connection: AsyncConnection, module: str, source: str, entity: EntityRef
) -> Resolution:
    await connection.execute(
        text("select pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{source}|{entity.alias}"}
    )

    existing = await connection.scalar(FIND_ALIAS, {"source": source, "alias": entity.alias})
    if existing is not None:
        return Resolution(entity_id=existing, created=False)

    entity_id = await connection.scalar(
        CREATE_CANDIDATE, {"kind": entity.kind, "module": module, "name": entity.alias}
    )
    await connection.execute(
        REGISTER_ALIAS,
        {
            "entity_id": str(entity_id),
            "alias": entity.alias,
            "source": source,
            "confidence": 1.0,
        },
    )
    return Resolution(entity_id=entity_id, created=True)


async def suggest(
    connection: AsyncConnection, module: str, kind: str, alias: str, exclude: UUID
) -> list[Suggestion]:
    rows = (
        await connection.execute(
            SUGGESTIONS,
            {
                "module": module,
                "kind": kind,
                "alias": alias,
                "exclude": str(exclude),
                "floor": SIMILARITY_FLOOR,
                "limit": MAX_SUGGESTIONS,
            },
        )
    ).all()
    return [
        Suggestion(id=row.id, name=row.name, kind=row.kind, score=float(row.score)) for row in rows
    ]


async def read_entity(connection: AsyncConnection, entity_id: UUID) -> Entity | None:
    parameters: dict[str, Any] = {"entity_id": str(entity_id)}
    row = (await connection.execute(READ_ENTITY, parameters)).one_or_none()
    if row is None:
        return None

    aliases = (await connection.execute(FAMILY_ALIASES, parameters)).all()
    merged = (await connection.execute(MERGED_INTO_THIS, parameters)).scalars().all()
    provenance = (await connection.execute(MERGED_VIA, parameters)).one_or_none()

    return Entity(
        id=row.id,
        kind=row.kind,
        module=row.module,
        name=row.name,
        status=row.status,
        merged_into=row.merged_into,
        aliases=[
            Alias(
                alias=alias.alias,
                source=alias.source,
                confidence=alias.confidence,
                entity_id=alias.entity_id,
                via=Provenance(
                    method=alias.method,
                    rule=alias.rule,
                    confidence=alias.decision_confidence,
                    evidence=alias.evidence,
                    decided_by=alias.decided_by,
                    decided_at=alias.decided_at,
                )
                if alias.method
                else None,
            )
            for alias in aliases
        ],
        merged=list(merged),
        merged_via=Provenance(
            method=provenance.method,
            rule=provenance.rule,
            confidence=provenance.confidence,
            evidence=provenance.evidence,
            decided_by=provenance.decided_by,
            decided_at=provenance.decided_at,
        )
        if provenance and row.status == "merged"
        else None,
    )


class SurvivingIn(BaseModel):
    ids: Annotated[list[UUID], Field(max_length=2000)]


class Surviving(BaseModel):
    id: UUID
    surviving: UUID
    name: str


SURVIVING = text("""
    select cast(asked.id as text) as id,
           cast(e.id as text) as surviving,
           e.name
    from unnest(cast(:ids as uuid[])) as asked(id)
    join kernel.entities e on e.id = kernel.surviving_entity(asked.id)
""")


@router.post("/entities/surviving")
async def surviving_entities(body: SurvivingIn) -> list[Surviving]:
    require_person()
    if not body.ids:
        return []
    async with engine().connect() as connection:
        rows = await connection.execute(SURVIVING, {"ids": [str(i) for i in body.ids]})
        return [Surviving(id=row.id, surviving=row.surviving, name=row.name) for row in rows]


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: Annotated[UUID, Path()]) -> Entity:
    async with engine().connect() as connection:
        entity = await read_entity(connection, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"entity '{entity_id}' does not exist")
    return entity


async def find_matches(connection: AsyncConnection, entity_id: UUID) -> Matches | None:
    subject = (await connection.execute(SUBJECT, {"entity_id": str(entity_id)})).one_or_none()
    if subject is None:
        return None

    mine = [subject.name, *subject.aliases]
    rows = (
        await connection.execute(
            MATCH_CANDIDATES,
            {"entity_id": str(entity_id), "module": subject.module, "kind": subject.kind},
        )
    ).all()

    candidates = []
    for row in rows:
        theirs = [row.name, *row.aliases]
        best: tuple[Match, str, str] | None = None
        for left in mine:
            for right in theirs:
                verdict = compare(left, right)
                if verdict is not None and (
                    best is None or verdict.confidence > best[0].confidence
                ):
                    best = (verdict, left, right)
        if best is None:
            continue
        verdict, left, right = best
        candidates.append(
            MatchCandidate(
                entity_id=row.id,
                name=row.name,
                status=row.status,
                rule=verdict.rule,
                confidence=verdict.confidence,
                evidence=verdict.evidence,
                matched=(left, right),
                would_merge=verdict.confidence >= AUTO_MERGE_CONFIDENCE,
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.confidence, candidate.name))
    return Matches(
        entity_id=entity_id,
        name=subject.name,
        threshold=AUTO_MERGE_CONFIDENCE,
        candidates=candidates,
    )


@router.get("/entities/{entity_id}/matches")
async def get_matches(entity_id: Annotated[UUID, Path()]) -> Matches:
    async with engine().connect() as connection:
        matches = await find_matches(connection, entity_id)
    if matches is None:
        raise HTTPException(status_code=404, detail=f"entity '{entity_id}' does not exist")
    return matches


async def surviving(connection: AsyncConnection, entity_id: str | UUID) -> str | None:
    return await connection.scalar(SURVIVOR, {"entity_id": str(entity_id)})


async def in_family(connection: AsyncConnection, target: str, candidate: str) -> bool:
    return bool(await connection.scalar(IN_FAMILY, {"target": target, "candidate": candidate}))


async def merge_entities(
    connection: AsyncConnection,
    candidate: str,
    target: str,
    *,
    method: str,
    decided_by: str,
    rule: str | None = None,
    confidence: float | None = None,
    evidence: str | None = None,
) -> None:
    await connection.execute(MERGE_ENTITY, {"candidate": candidate, "target": target})
    await connection.execute(RESOLVE_FAMILY, {"entity_id": target})
    await connection.execute(
        RECORD_DECISION,
        {
            "loser": candidate,
            "winner": target,
            "decision": "merged",
            "method": method,
            "rule": rule,
            "confidence": confidence,
            "evidence": evidence,
            "decided_by": decided_by,
        },
    )


async def last_word(connection: AsyncConnection, left: str, right: str) -> str | None:
    return await connection.scalar(LAST_WORD, {"left": left, "right": right})


async def unmerge_entity(
    connection: AsyncConnection, entity_id: str, *, decided_by: str, evidence: str | None = None
) -> str | None:
    winner = await connection.scalar(
        text(
            "select cast(merged_into as text) from kernel.entities "
            "where id = cast(:entity_id as uuid) and status = 'merged'"
        ),
        {"entity_id": entity_id},
    )
    if winner is None:
        return None

    await connection.execute(DETACH, {"entity_id": entity_id})
    await connection.execute(
        RECORD_DECISION,
        {
            "loser": entity_id,
            "winner": winner,
            "decision": "rejected",
            "method": "undo",
            "rule": None,
            "confidence": None,
            "evidence": evidence,
            "decided_by": decided_by,
        },
    )
    return winner


@router.post("/entities/{entity_id}/unmerge")
async def unmerge(entity_id: Annotated[UUID, Path()]) -> Entity:
    require_person()
    async with engine().begin() as connection:
        winner = await unmerge_entity(connection, str(entity_id), decided_by="person")
        if winner is None:
            raise HTTPException(
                status_code=409, detail=f"entity '{entity_id}' is not merged into anything"
            )
        entity = await read_entity(connection, entity_id)
    return entity


class Decision(BaseModel):
    id: UUID
    loser_id: UUID
    loser_name: str
    winner_id: UUID
    winner_name: str
    decision: str
    method: str
    rule: str | None
    confidence: float | None
    evidence: str | None
    decided_by: str
    decided_at: datetime


@router.get("/resolutions")
async def list_decisions(
    entity_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[Decision]:
    async with engine().connect() as connection:
        rows = (
            await connection.execute(
                DECISIONS,
                {"entity_id": str(entity_id) if entity_id else None, "limit": limit},
            )
        ).all()
    return [Decision(**row._mapping) for row in rows]
