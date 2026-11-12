from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from training import training

TYPE = "training.variant"
APP = "training"

VARIANTS = text("""
    select v.id, v.name as variant, v.active, e.name as exercise
    from training.training_variant v
    join training.training_exercise e on e.id = v.exercise_id
""")


def label(exercise: str, variant: str) -> str:
    if exercise.casefold() in variant.casefold():
        return variant
    return f"{exercise} · {variant}"


def payload(row) -> dict[str, Any]:
    return {
        contracts.LINKABLE: contracts.linkable(
            id=str(row.id),
            title=label(row.exercise, row.variant)[:200],
            kind="Exercise",
            href=f"/training/stats?variant={row.id}",
            removed=not row.active,
        ),
        "variant_id": str(row.id),
    }


async def _publish(connection: AsyncConnection, row) -> None:
    title = label(row.exercise, row.variant)
    await training.enqueue(
        connection,
        TYPE,
        datetime.now(UTC),
        payload(row),
        f"training:variant:{row.id}:linkable:{title}:{row.active}",
    )


async def variant_changed(connection: AsyncConnection, variant_id: str) -> None:
    row = (
        await connection.execute(text(f"{VARIANTS.text} where v.id = :id"), {"id": variant_id})
    ).one_or_none()
    if row is not None:
        await _publish(connection, row)


async def exercise_changed(connection: AsyncConnection, exercise_id: str) -> None:
    rows = (
        await connection.execute(
            text(f"{VARIANTS.text} where v.exercise_id = :id"), {"id": exercise_id}
        )
    ).all()
    for row in rows:
        await _publish(connection, row)


async def backfill(connection: AsyncConnection) -> int:
    rows = (await connection.execute(VARIANTS)).all()
    for row in rows:
        await _publish(connection, row)
    return len(rows)


MENTIONS = text(f"""
    select distinct on (payload->'{contracts.MENTION}'->>'note_id')
        payload->'{contracts.MENTION}' as mention
    from training.events
    where payload ? '{contracts.MENTION}'
      and payload->'{contracts.MENTION}'->>'app' = '{APP}'
      and payload->'{contracts.MENTION}'->>'id' = :id
    order by payload->'{contracts.MENTION}'->>'note_id', ts desc, ingested_at desc
""")


async def notes_about(connection: AsyncConnection, variant_id: str) -> list[dict[str, str]]:
    rows = (await connection.execute(MENTIONS, {"id": variant_id})).all()
    return sorted(
        (
            {"title": m["note_title"], "href": m["note_href"], "line": m.get("line") or ""}
            for m in (row.mention for row in rows)
            if not m.get("removed")
        ),
        key=lambda one: one["title"].casefold(),
    )
