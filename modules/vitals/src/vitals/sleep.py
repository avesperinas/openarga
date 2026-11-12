from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals.steps import Period, arrived, start_of, today

Stage = Literal["awake", "light", "deep", "rem", "asleep", "restless"]
STAGES = ("deep", "rem", "light", "awake")

LATEST = text("""
    select distinct on (payload->>'id') payload
    from vitals.events
    where type = 'health.sleep'
    order by payload->>'id', ingested_at desc, ts desc
""")

BETWEEN = text("""
    select payload, ingested_at, ts from (
        select distinct on (payload->>'id') payload, ingested_at, ts
        from vitals.events
        where type = 'health.sleep' and ingested_at >= :arrived
        order by payload->>'id', ingested_at desc, ts desc
    ) as latest
    where (payload->>'date')::date between :since and :until
""")

ARRIVED = text("""
    select distinct on (payload->>'id') payload, ingested_at, ts
    from vitals.events
    where type = 'health.sleep' and ingested_at > :after
    order by payload->>'id', ingested_at desc, ts desc
""")


class Segment(BaseModel):
    start: datetime
    end: datetime
    stage: Stage


FULL_SLEEP = 480
DEEP_SHARE = 0.45
AWAKE_FULL, AWAKE_EMPTY = 0.05, 0.25

Quality = Literal["excellent", "good", "fair", "poor"]


class Score(BaseModel):
    value: int
    quality: Quality
    duration: float
    depth: float | None
    calm: float | None


def quality(value: int) -> Quality:
    if value >= 90:
        return "excellent"
    return "good" if value >= 80 else "fair" if value >= 60 else "poor"


def score(asleep: int, stages: dict[str, int] | None, minutes_awake: int | None) -> Score | None:
    if asleep <= 0:
        return None
    duration = 50 * min(1.0, asleep / FULL_SLEEP)
    depth = calm = None
    if stages and (stages.get("deep") is not None or stages.get("rem") is not None):
        deep = (stages.get("deep") or 0) + (stages.get("rem") or 0)
        depth = 25 * min(1.0, deep / asleep / DEEP_SHARE)
    awake = (stages or {}).get("awake", minutes_awake)
    if awake is not None:
        share = awake / (asleep + awake)
        calm = 25 * max(0.0, min(1.0, (AWAKE_EMPTY - share) / (AWAKE_EMPTY - AWAKE_FULL)))
    parts = [duration, depth, calm]
    top = 50 + (25 if depth is not None else 0) + (25 if calm is not None else 0)
    value = round(sum(one for one in parts if one is not None) / top * 100)
    return Score(
        value=value,
        quality=quality(value),
        duration=round(duration, 1),
        depth=None if depth is None else round(depth, 1),
        calm=None if calm is None else round(calm, 1),
    )


class Night(BaseModel):
    day: date
    start: datetime
    end: datetime
    minutes_asleep: int
    minutes_awake: int | None = None
    minutes_in_bed: int | None = None
    minutes_to_fall_asleep: int | None = None
    stages: dict[str, int] | None = None
    nap_minutes: int = 0
    awakenings: int | None = None
    minutes_after_wake_up: int | None = None
    minutes_out_of_bed: int | None = None
    score: Score | None = None


class NightDetail(Night):
    segments: list[Segment]


class Means(BaseModel):
    nights: int
    asleep: int | None
    stages: dict[str, int]
    fell_asleep_at: int | None
    woke_at: int | None


class Summary(BaseModel):
    last: NightDetail | None
    nights: list[Night]
    mean_7: Means
    mean_30: Means


class Bucket(BaseModel):
    start: date
    nights: int
    asleep: int
    stages: dict[str, int]


def fell_asleep_after(given: int | None, segments: list[dict]) -> int | None:
    awake = 0.0
    for one in sorted(segments, key=lambda segment: segment["start"]):
        if one.get("stage") not in ("awake", "restless"):
            break
        awake += (
            datetime.fromisoformat(one["end"]) - datetime.fromisoformat(one["start"])
        ).total_seconds() / 60
    if given is None and not segments:
        return None
    return max(given or 0, round(awake))


async def read(
    connection: AsyncConnection, since: date = date.min, until: date = date.max
) -> list[NightDetail]:
    if since == date.min and until == date.max:
        rows = await connection.execute(LATEST)
    else:
        rows = await connection.execute(
            BETWEEN, {"since": since, "until": until, "arrived": arrived(since)}
        )
    return nights_of([row.payload for row in rows.all()], since, until)


async def raw(connection: AsyncConnection, since: date, until: date) -> list[Any]:
    found = await connection.execute(
        BETWEEN, {"since": since, "until": until, "arrived": arrived(since)}
    )
    return found.all()


async def arrived_since(connection: AsyncConnection, after: datetime) -> list[Any]:
    return (await connection.execute(ARRIVED, {"after": after})).all()


def nights_of(payloads: list[dict], since: date, until: date) -> list[NightDetail]:
    by_day: dict[date, list[dict]] = {}
    for payload in payloads:
        day = date.fromisoformat(payload["date"])
        if since <= day <= until:
            by_day.setdefault(day, []).append(payload)
    nights = []
    for day, found in sorted(by_day.items()):
        main = max(found, key=lambda one: (bool(one.get("main", True)), one["minutes_asleep"]))
        naps = sum(one["minutes_asleep"] for one in found if one is not main)
        nights.append(
            NightDetail(
                day=day,
                start=main["start"],
                end=main["end"],
                minutes_asleep=main["minutes_asleep"],
                minutes_awake=main.get("minutes_awake"),
                minutes_in_bed=main.get("minutes_in_bed"),
                minutes_to_fall_asleep=fell_asleep_after(
                    main.get("minutes_to_fall_asleep"), main.get("segments") or []
                ),
                stages=main.get("stages"),
                nap_minutes=naps,
                awakenings=main.get("awakenings"),
                minutes_after_wake_up=main.get("minutes_after_wake_up"),
                minutes_out_of_bed=main.get("minutes_out_of_bed"),
                segments=main.get("segments") or [],
                score=score(main["minutes_asleep"], main.get("stages"), main.get("minutes_awake")),
            )
        )
    return nights


def clock(moment: datetime) -> int:
    minutes = moment.hour * 60 + moment.minute
    return minutes - 1440 if minutes >= 12 * 60 else minutes


def means(nights: list[Night]) -> Means:
    if not nights:
        return Means(nights=0, asleep=None, stages={}, fell_asleep_at=None, woke_at=None)
    staged = [one for one in nights if one.stages]
    return Means(
        nights=len(nights),
        asleep=round(sum(one.minutes_asleep for one in nights) / len(nights)),
        stages={
            stage: round(sum((one.stages or {}).get(stage, 0) for one in staged) / len(staged))
            for stage in STAGES
            if staged
        },
        fell_asleep_at=round(sum(clock(one.start) for one in nights) / len(nights)),
        woke_at=round(sum(clock(one.end) for one in nights) / len(nights)),
    )


def plain(night: NightDetail) -> Night:
    return Night(**night.model_dump(exclude={"segments"}))


async def summary(
    connection: AsyncConnection, since: date | None = None, until: date | None = None
) -> Summary:
    now = today()
    since = since or now - timedelta(days=89)
    until = until or now
    found = await read(connection, min(since, now - timedelta(days=29)))
    last = found[-1] if found else None
    if last is None:
        every = await read(connection)
        last = every[-1] if every else None
    return Summary(
        last=last,
        nights=[plain(one) for one in found if since <= one.day <= until],
        mean_7=means([one for one in found if one.day > now - timedelta(days=7)]),
        mean_30=means([one for one in found if one.day > now - timedelta(days=30)]),
    )


async def night(connection: AsyncConnection, day: date) -> NightDetail | None:
    return next((one for one in await read(connection, day, day) if one.day == day), None)


def buckets(nights: list[Night], period: Period) -> list[Bucket]:
    grouped: dict[date, list[Night]] = {}
    for one in nights:
        grouped.setdefault(start_of(one.day, period), []).append(one)
    out = []
    for start, found in sorted(grouped.items()):
        mean = means(found)
        out.append(
            Bucket(start=start, nights=len(found), asleep=mean.asleep or 0, stages=mean.stages)
        )
    return out
