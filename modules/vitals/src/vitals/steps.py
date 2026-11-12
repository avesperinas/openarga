from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals import memo

MADRID = ZoneInfo("Europe/Madrid")
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

Period = Literal["day", "week", "month", "year"]

STARTED = """
    started as (
        select source, min((payload->>'date')::date) as since from vitals.events
        where type in ('health.daily', 'health.steps')
        group by source
    )
"""

EARLY = timedelta(days=2)

LATEST = text("""
    select distinct on ((payload->>'date')::date, source)
        (payload->>'date')::date as day,
        source,
        (payload->>'steps')::int as steps,
        ingested_at,
        ts
    from vitals.events
    where type = 'health.steps' and ingested_at >= :arrived
      and (payload->>'date')::date between :since and :until
    order by (payload->>'date')::date, source, ingested_at desc, ts desc
""")

ANY = text("select exists (select 1 from vitals.events where type = 'health.steps')")


def arrived(since: date) -> datetime:
    return datetime.combine(max(since, date.min + EARLY) - EARLY, time(), UTC)


Started = dict[str, date | None]


STARTED_TYPES = ("health.daily", "health.steps")

FIRSTS_WITH_LAST = text(f"""
    with {STARTED}
    select started.source, started.since, (
        select max(ingested_at) from vitals.events
        where type in ('health.daily', 'health.steps')
    ) as last
    from started
""")

FIRSTS_SINCE = text("""
    select source, min((payload->>'date')::date) as since, max(ingested_at) as last
    from vitals.events
    where type in ('health.daily', 'health.steps') and ingested_at > :after
    group by source
""")


class _Starts(memo.Read):
    def __init__(self, found: Started, last: datetime | None) -> None:
        super().__init__()
        self.found = found
        self.last = last


async def started(connection: AsyncConnection) -> Started:
    kept = memo.get("started")
    if kept is None or kept.expired():
        rows = (await connection.execute(FIRSTS_WITH_LAST)).all()
        kept = _Starts({row.source: row.since for row in rows}, rows[0].last if rows else None)
    else:
        rows = (await connection.execute(FIRSTS_SINCE, {"after": memo.after(kept.last)})).all()
        for row in rows:
            before = kept.found.get(row.source)
            kept.found[row.source] = row.since if before is None else min(before, row.since)
        kept.last = memo.latest(kept.last, *(row.last for row in rows))
    memo.put("started", None, kept)
    return kept.found


def switch(found: Started) -> date | None:
    if len(found) < 2:
        return None
    return max((since for since in found.values() if since is not None), default=None)


async def winners(
    connection: AsyncConnection,
    rows: Sequence[Any],
    key: Callable[[Any], Hashable],
    started_on: Started | None = None,
) -> list[Any]:
    if started_on is None and _two_sources(rows, key):
        started_on = await started(connection)
    return choose(rows, key, started_on or {})


def _two_sources(rows: Sequence[Any], key: Callable[[Any], Hashable]) -> bool:
    seen: set[Hashable] = set()
    for row in rows:
        group = key(row)
        if group in seen:
            return True
        seen.add(group)
    return False


def choose(rows: Sequence[Any], key: Callable[[Any], Hashable], known: Started) -> list[Any]:
    groups: dict[Hashable, list[Any]] = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)

    def rank(row: Any) -> tuple:
        since = known.get(row.source)
        return (since is not None, since or date.min, row.ingested_at, row.ts)

    return [found[0] if len(found) == 1 else max(found, key=rank) for found in groups.values()]


class StepsDay(BaseModel):
    day: date
    steps: int


class Bucket(BaseModel):
    start: date
    total: int
    days: int
    mean: int


class Summary(BaseModel):
    days: list[StepsDay]
    today: StepsDay | None
    mean_7: int | None
    mean_30: int | None
    goal: int | None
    best: StepsDay | None
    streak: int
    by_weekday: list[int | None]
    last_received: datetime | None


def today() -> date:
    return datetime.now(MADRID).date()


async def read(
    connection: AsyncConnection, since: date = date.min, until: date = date.max
) -> tuple[list[StepsDay], datetime | None]:
    found = await connection.execute(
        LATEST, {"arrived": arrived(since), "since": since, "until": until}
    )
    rows = await winners(connection, found.all(), key=lambda row: row.day)
    received = max((row.ingested_at for row in rows), default=None)
    return [StepsDay(day=row.day, steps=row.steps) for row in rows], received


async def any_steps(connection: AsyncConnection) -> bool:
    return bool(await connection.scalar(ANY))


def mean_of(days: list[StepsDay], since: date, until: date) -> int | None:
    values = [one.steps for one in days if since <= one.day <= until]
    return round(sum(values) / len(values)) if values else None


def streak(days: list[StepsDay], goal: int | None, now: date) -> int:
    if not goal:
        return 0
    by_day = {one.day: one.steps for one in days}
    cursor = now if by_day.get(now, 0) >= goal else now - timedelta(days=1)
    count = 0
    while by_day.get(cursor, -1) >= goal:
        count += 1
        cursor -= timedelta(days=1)
    return count


def by_weekday(days: list[StepsDay]) -> list[int | None]:
    sums = [0] * 7
    counts = [0] * 7
    for one in days:
        sums[one.day.weekday()] += one.steps
        counts[one.day.weekday()] += 1
    return [round(sums[i] / counts[i]) if counts[i] else None for i in range(7)]


def start_of(day: date, period: Period) -> date:
    if period == "week":
        return day - timedelta(days=day.weekday())
    if period == "month":
        return day.replace(day=1)
    if period == "year":
        return day.replace(month=1, day=1)
    return day


def buckets(days: list[StepsDay], period: Period) -> list[Bucket]:
    grouped: dict[date, list[int]] = {}
    for one in days:
        grouped.setdefault(start_of(one.day, period), []).append(one.steps)
    return [
        Bucket(
            start=start, total=sum(values), days=len(values), mean=round(sum(values) / len(values))
        )
        for start, values in sorted(grouped.items())
    ]


def summarise(
    days: list[StepsDay], goal: int | None, received: datetime | None, now: date
) -> Summary:
    return Summary(
        days=days,
        today=next((one for one in days if one.day == now), None),
        mean_7=mean_of(days, now - timedelta(days=6), now),
        mean_30=mean_of(days, now - timedelta(days=29), now),
        goal=goal,
        best=max(days, key=lambda one: (one.steps, one.day), default=None),
        streak=streak(days, goal, now),
        by_weekday=by_weekday(days),
        last_received=received,
    )


async def summary(connection: AsyncConnection, goal: int | None) -> Summary:
    days, received = await read(connection)
    return summarise(days, goal, received, today())
