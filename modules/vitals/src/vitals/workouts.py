from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from vitals import body, heart, memo
from vitals.steps import arrived, today, zone

_WORKOUTS = f"""
    select distinct on (payload->'{contracts.WORKOUT}'->>'id')
        id as version, payload->'{contracts.WORKOUT}' as w, ingested_at, ts
    from vitals.events
    where type not like 'health.%' and {{arrival}}
      and (payload @> '{{{{"{contracts.WORKOUT}": {{{{"kind": "strength"}}}}}}}}'
           or payload @> '{{{{"{contracts.WORKOUT}": {{{{"kind": "activity"}}}}}}}}')
    order by payload->'{contracts.WORKOUT}'->>'id', ingested_at desc, ts desc
"""
WORKOUTS = text(_WORKOUTS.format(arrival="ingested_at >= :arrived"))
WORKOUTS_ARRIVED = text(_WORKOUTS.format(arrival="ingested_at > :after"))

_EXERCISES = """
    select distinct on (payload->>'id') payload->>'id' as band, id as version, ingested_at, ts
    from vitals.events
    where type = 'health.exercise' and {arrival}
    order by payload->>'id', ingested_at desc, ts desc
"""
EXERCISES = text(_EXERCISES.format(arrival="payload->>'id' = any(cast(:ids as text[]))"))
EXERCISES_ARRIVED = text(_EXERCISES.format(arrival="ingested_at > :after"))
EXERCISE_PAYLOADS = text("""
    select payload from vitals.events
    where type = 'health.exercise' and id = any(cast(:versions as uuid[]))
""")

NOW = text("select now()")

ZONES = (0.5, 0.6, 0.7, 0.8, 0.9)
DEFAULT_MAX = 190


class Beat(BaseModel):
    s: int
    bpm: float


class Mark(BaseModel):
    at: datetime
    label: str


class Heart(BaseModel):
    avg: float | None
    max: float | None
    zones: list[float]
    load: float
    recovery_2min: float | None
    source: Literal["band", "day"] | None


class Workout(BaseModel):
    id: str
    kind: Literal["strength", "activity"]
    name: str
    start: datetime
    end: datetime
    minutes: int
    href: str | None
    from_band: bool
    kcal: float | None
    heart: Heart


class WorkoutDetail(Workout):
    beats: list[Beat]
    marks: list[Mark]
    max_heart_rate: int


class Week(BaseModel):
    start: date
    workouts: int
    minutes: int
    load: float
    zones: list[float] = [0.0] * 5


class Load(BaseModel):
    this_week: float
    mean_4: float | None
    weeks: list[Week]


async def max_heart_rate(connection: AsyncConnection) -> int:
    found = await body.profile(connection)
    if found is None or found.age is None:
        return DEFAULT_MAX
    return 220 - found.age


@dataclass
class Kept(memo.Read):
    found: dict[str, Any] = field(default_factory=dict)
    last: datetime | None = None
    asked: set[str] = field(default_factory=set)

    def merge(self, rows: list[Any], key: Callable[[Any], str]) -> None:
        for row in rows:
            before = self.found.get(key(row))
            if before is None or (row.ingested_at, row.ts) >= (before.ingested_at, before.ts):
                self.found[key(row)] = row
        self.last = memo.latest(self.last, *(row.ingested_at for row in rows))


async def _done(connection: AsyncConnection) -> list[dict]:
    kept: Kept | None = memo.get("workouts")
    if kept is None or kept.expired():
        kept = Kept(last=await connection.scalar(NOW))
        rows = (await connection.execute(WORKOUTS, {"arrived": arrived(date.min)})).all()
    else:
        rows = (await connection.execute(WORKOUTS_ARRIVED, {"after": memo.after(kept.last)})).all()
    kept.merge(rows, key=lambda row: row.w["id"])
    memo.put("workouts", None, kept)
    return [
        {**row.w, VERSION: row.version}
        for _, row in sorted(kept.found.items())
        if not row.w.get("removed")
    ]


VERSION = "_version"


def started_on(found: dict) -> date:
    return datetime.fromisoformat(found["start"]).astimezone(zone()).date()


async def _exercise_versions(connection: AsyncConnection, done: list[dict]) -> dict[str, Any]:
    ids = sorted({found["band_id"] for found in done if found.get("band_id")})
    if not ids:
        return {}
    kept: Kept | None = memo.get("exercises")
    if kept is None or kept.expired():
        kept = Kept(last=await connection.scalar(NOW))
    else:
        after = memo.after(kept.last)
        rows = (await connection.execute(EXERCISES_ARRIVED, {"after": after})).all()
        kept.merge(rows, key=lambda row: row.band)
    missing = [one for one in ids if one not in kept.asked]
    if missing:
        rows = (await connection.execute(EXERCISES, {"ids": missing})).all()
        kept.merge(rows, key=lambda row: row.band)
        kept.asked.update(row.band for row in rows)
    memo.put("exercises", None, kept)
    return {one: kept.found[one] for one in ids if one in kept.found}


async def _exercise_payloads(connection: AsyncConnection, versions: dict[str, Any]) -> dict:
    if not versions:
        return {}
    rows = await connection.execute(
        EXERCISE_PAYLOADS, {"versions": [row.version for row in versions.values()]}
    )
    return {
        row.payload["id"]: {**row.payload, VERSION: versions[row.payload["id"]].version}
        for row in rows.all()
        if row.payload["id"] in versions
    }


async def _exercises(connection: AsyncConnection, done: list[dict]) -> dict[str, dict]:
    return await _exercise_payloads(connection, await _exercise_versions(connection, done))


Days = dict[date, dict]


async def heart_days(
    connection: AsyncConnection, first: date, last: date, wanted: set[date] | None = None
) -> Days:
    if wanted is None:
        wanted = {first + timedelta(days=n) for n in range((last - first).days + 1)}
    return await heart.latest(connection, [one for one in wanted if first <= one <= last])


def spanned(found: dict) -> set[date]:
    first = datetime.fromisoformat(found["start"]).astimezone(zone()).date()
    last = (datetime.fromisoformat(found["end"]) + timedelta(minutes=3)).astimezone(zone()).date()
    return {first + timedelta(days=n) for n in range((last - first).days + 1)}


async def _day_beats(
    connection: AsyncConnection, start: datetime, end: datetime, days: Days | None = None
) -> list[Beat]:
    first, last = start.astimezone(zone()), (end + timedelta(minutes=3)).astimezone(zone())
    if days is None:
        days = await heart_days(connection, first.date(), last.date())
    beats = []
    for day, payload in sorted(days.items()):
        if not first.date() <= day <= last.date():
            continue
        midnight = datetime.combine(day, datetime.min.time(), zone())
        for bucket in payload.get("buckets", []):
            moment = midnight + timedelta(minutes=bucket["minute"])
            if first <= moment < last:
                beats.append(Beat(s=round((moment - start).total_seconds()), bpm=bucket["avg"]))
    return sorted(beats, key=lambda one: one.s)


def heart_of(beats: list[Beat], seconds: int, top: int, source: str | None) -> Heart:
    inside = [one for one in beats if 0 <= one.s < seconds]
    zones = [0.0] * 5
    load = 0.0
    for index, one in enumerate(inside):
        following = inside[index + 1].s if index + 1 < len(inside) else seconds
        span = max(0, min(following, seconds) - one.s) / 60
        level = sum(1 for edge in ZONES if one.bpm >= edge * top)
        if level:
            zones[level - 1] += span
            load += span * level
    after = [one for one in beats if seconds <= one.s <= seconds + 150]
    last = inside[-1].bpm if inside else None
    recovery = None
    if last is not None and after:
        recovery = round(last - min(one.bpm for one in after), 1)
    values = [one.bpm for one in inside]
    return Heart(
        avg=round(sum(values) / len(values), 1) if values else None,
        max=max(values) if values else None,
        zones=[round(one, 1) for one in zones],
        load=round(load, 1),
        recovery_2min=recovery,
        source=source if values else None,
    )


async def _build(
    connection: AsyncConnection,
    found: dict,
    exercises: dict[str, dict],
    top: int,
    detail: bool = False,
    days: Days | None = None,
):
    start = datetime.fromisoformat(found["start"])
    end = datetime.fromisoformat(found["end"])
    seconds = max(0, round((end - start).total_seconds()))
    band = exercises.get(found.get("band_id") or "")
    beats: list[Beat] = []
    source = None
    if band and band.get("heart"):
        began = datetime.fromisoformat(band["start"])
        shift = round((began - start).total_seconds())
        beats = [Beat(s=one["s"] + shift, bpm=one["bpm"]) for one in band["heart"]]
        source = "band"
        tail = [one for one in await _day_beats(connection, end, end, days) if one.s >= 0]
        beats += [Beat(s=one.s + seconds, bpm=one.bpm) for one in tail]
    else:
        beats = await _day_beats(connection, start, end, days)
        source = "day"
    heart = heart_of(beats, seconds, top, source)
    if band and band.get("heart_rate_avg") and heart.avg is None:
        heart.avg = band["heart_rate_avg"]
    fields = {
        "id": found["id"],
        "kind": found["kind"],
        "name": found["name"],
        "start": start,
        "end": end,
        "minutes": round(seconds / 60),
        "href": found.get("href"),
        "from_band": band is not None,
        "kcal": band.get("kcal") if band else None,
        "heart": heart,
    }
    if not detail:
        return Workout(**fields)
    return WorkoutDetail(
        **fields,
        beats=[one for one in beats if one.s <= seconds + 150],
        marks=[Mark(**one) for one in found.get("marks", [])],
        max_heart_rate=top,
    )


async def between(connection: AsyncConnection, first: date, last: date) -> list[Workout]:
    done = await _done(connection)
    inside = [found for found in done if first <= started_on(found) <= last]
    if not inside:
        return []
    bands = await _exercise_versions(connection, inside)
    top = await max_heart_rate(connection)
    versions = await heart.chosen(connection, sorted(set().union(*map(spanned, inside))))
    out, missing = [], []
    for found in inside:
        key = built_key(found, bands, versions, top)
        if key in BUILT:
            BUILT.move_to_end(key)
            out.append(BUILT[key])
        else:
            missing.append((key, found))
    if missing:
        needed = set().union(*(spanned(found) for _, found in missing))
        days = await heart.payloads(
            connection, [versions[day] for day in needed if day in versions]
        )
        wanted = {found.get("band_id") for _, found in missing}
        exercises = await _exercise_payloads(
            connection, {band: row for band, row in bands.items() if band in wanted}
        )
        for key, found in missing:
            made = await _build(connection, found, exercises, top, days=days)
            BUILT[key] = made
            out.append(made)
        while len(BUILT) > BUILT_SIZE:
            BUILT.popitem(last=False)
    return sorted(sorted(out, key=lambda one: one.id), key=lambda one: one.start, reverse=True)


BUILT: OrderedDict[tuple, Workout] = OrderedDict()
BUILT_SIZE = 4096


def built_key(found: dict, bands: dict[str, Any], versions: dict, top: int) -> tuple:
    band = bands.get(found.get("band_id") or "")
    days = tuple(versions.get(day) for day in sorted(spanned(found)))
    return (found[VERSION], band.version if band else None, days, top)


async def spans(
    connection: AsyncConnection, first: date, last: date
) -> list[tuple[datetime, datetime]]:
    out = []
    for found in await _done(connection):
        start = datetime.fromisoformat(found["start"])
        if first <= start.astimezone(zone()).date() <= last:
            out.append((start, datetime.fromisoformat(found["end"])))
    return sorted(out)


async def one(connection: AsyncConnection, workout_id: str) -> WorkoutDetail | None:
    for found in await _done(connection):
        if found["id"] == workout_id:
            top = await max_heart_rate(connection)
            return await _build(connection, found, await _exercises(connection, [found]), top, True)
    return None


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


async def load(
    connection: AsyncConnection,
    weeks: int = 12,
    now: date | None = None,
    done: list[Workout] | None = None,
) -> Load:
    now = now or today()
    first = monday(now) - timedelta(weeks=weeks - 1)
    if done is None:
        done = await between(connection, first, now)
    done = [one for one in done if first <= one.start.astimezone(zone()).date() <= now]
    by_week: dict[date, list[Workout]] = {first + timedelta(weeks=i): [] for i in range(weeks)}
    for one in done:
        by_week.setdefault(monday(one.start.astimezone(zone()).date()), []).append(one)
    out = [
        Week(
            start=start,
            workouts=len(found),
            minutes=sum(one.minutes for one in found),
            load=round(sum(one.heart.load for one in found), 1),
            zones=[round(sum(one.heart.zones[i] for one in found), 1) for i in range(5)],
        )
        for start, found in sorted(by_week.items())
    ]
    before = [one.load for one in out[-5:-1]]
    return Load(
        this_week=out[-1].load if out else 0.0,
        mean_4=round(sum(before) / len(before), 1) if len(before) == 4 else None,
        weeks=out,
    )
