from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals.steps import arrived, today

CHOSEN = text("""
    select distinct on ((ts at time zone 'UTC')::date) (ts at time zone 'UTC')::date as day, id
    from vitals.events
    where type = 'health.heart' and ingested_at >= :arrived and ts >= :first and ts < :after
      and (ts at time zone 'UTC')::date = any(cast(:days as date[]))
    order by (ts at time zone 'UTC')::date, ingested_at desc, ts desc
""")

PAYLOADS = text("""
    select payload from vitals.events
    where type = 'health.heart' and id = any(cast(:ids as uuid[]))
""")

DAYS = text("""
    select distinct (ts at time zone 'UTC')::date as day from vitals.events
    where type = 'health.heart' and ingested_at >= :arrived
    order by day desc
    limit :limit
""")


def utc_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), UTC)


async def chosen(connection: AsyncConnection, days: list[date]) -> dict[date, UUID]:
    if not days:
        return {}
    first, last = min(days), max(days)
    rows = await connection.execute(
        CHOSEN,
        {
            "arrived": arrived(first),
            "first": utc_midnight(first),
            "after": utc_midnight(last + timedelta(days=1)),
            "days": sorted(days),
        },
    )
    return {row.day: row.id for row in rows.all()}


async def payloads(connection: AsyncConnection, ids: list[UUID]) -> dict[date, dict]:
    if not ids:
        return {}
    rows = await connection.execute(PAYLOADS, {"ids": ids})
    return {date.fromisoformat(row.payload["date"]): row.payload for row in rows.all()}


async def latest(connection: AsyncConnection, days: list[date]) -> dict[date, dict]:
    return await payloads(connection, list((await chosen(connection, days)).values()))


class Bucket(BaseModel):
    minute: int
    min: float
    avg: float
    max: float
    steps: int | None = None


class Hour(BaseModel):
    hour: int
    min: float
    avg: float
    max: float


class Day(BaseModel):
    day: date
    step: int
    buckets: list[Bucket]
    min: Bucket | None
    max: Bucket | None


async def days(connection: AsyncConnection, limit: int = 120) -> list[date]:
    since = today() - timedelta(days=limit)
    for bound in (since, date.min):
        found = await connection.execute(DAYS, {"limit": limit, "arrived": arrived(bound)})
        out = [row.day for row in found.all()]
        if out and len(out) == limit and out[-1] >= since:
            break
    return out


async def of_day(connection: AsyncConnection, day: date) -> Day | None:
    payload = (await latest(connection, [day])).get(day)
    if payload is None:
        return None
    buckets = [Bucket.model_validate(one) for one in payload["buckets"]]
    return Day(
        day=day,
        step=payload["step"],
        buckets=buckets,
        min=min(buckets, key=lambda one: one.min) if buckets else None,
        max=max(buckets, key=lambda one: one.max) if buckets else None,
    )


def hours(found: Day) -> list[Hour]:
    grouped: dict[int, list[Bucket]] = {}
    for one in found.buckets:
        grouped.setdefault(one.minute // 60, []).append(one)
    return [
        Hour(
            hour=hour,
            min=min(one.min for one in items),
            avg=round(sum(one.avg for one in items) / len(items), 1),
            max=max(one.max for one in items),
        )
        for hour, items in sorted(grouped.items())
    ]
