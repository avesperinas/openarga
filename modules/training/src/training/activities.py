from __future__ import annotations

import json
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from training import agenda
from training.training import Conflict, NotFound, enqueue, zone

Name = Annotated[str, Field(min_length=1, max_length=60, pattern=r"\S")]
Notes = Annotated[str, Field(max_length=2000)]


BandKind = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[A-Z0-9_]+$")]


class ActivityType(BaseModel):
    id: str
    name: str
    active: bool
    band_kinds: list[str] = []


class ActivityTypeIn(BaseModel):
    name: Name
    active: bool = True
    band_kinds: list[BandKind] | None = Field(default=None, max_length=20)


class Activity(BaseModel):
    id: str
    activity_type_id: str
    name: str
    day: date
    start_time: time
    duration_seconds: int | None
    notes: str | None
    source: str = "app"
    band: dict[str, Any] | None = None
    from_band: bool = False
    ongoing: bool = False


class ActivityIn(BaseModel):
    activity_type_id: str
    day: date
    start_time: time | None = None
    duration_seconds: Annotated[int, Field(ge=0, le=86400)] | None = None
    notes: Notes | None = None


async def types(connection: AsyncConnection) -> list[ActivityType]:
    rows = await connection.execute(
        text(
            "select id, name, active, band_kinds from training.training_activity_type "
            "order by lower(name)"
        )
    )
    return [
        ActivityType(
            id=str(row.id), name=row.name, active=row.active, band_kinds=list(row.band_kinds)
        )
        for row in rows
    ]


async def create_type(connection: AsyncConnection, request: ActivityTypeIn) -> ActivityType:
    name = request.name.strip()
    found = (
        await connection.execute(
            text(
                "select id, name, active, band_kinds from training.training_activity_type "
                "where lower(btrim(name)) = lower(:name)"
            ),
            {"name": name},
        )
    ).one_or_none()
    if found:
        return ActivityType(
            id=str(found.id), name=found.name, active=found.active, band_kinds=found.band_kinds
        )
    kinds = sorted(set(request.band_kinds or []))
    type_id = await connection.scalar(
        text(
            "insert into training.training_activity_type (name, active, band_kinds) "
            "values (:name, :active, :kinds) returning id"
        ),
        {"name": name, "active": request.active, "kinds": kinds},
    )
    return ActivityType(id=str(type_id), name=name, active=request.active, band_kinds=kinds)


async def update_type(
    connection: AsyncConnection, type_id: str, request: ActivityTypeIn
) -> ActivityType:
    row = (
        await connection.execute(
            text(
                "update training.training_activity_type set name = :name, active = :active, "
                "band_kinds = coalesce(cast(:kinds as text[]), band_kinds) "
                "where id = cast(:id as uuid) returning id, band_kinds"
            ),
            {
                "name": request.name.strip(),
                "active": request.active,
                "kinds": None if request.band_kinds is None else sorted(set(request.band_kinds)),
                "id": type_id,
            },
        )
    ).one_or_none()
    if row is None:
        raise NotFound(type_id)
    return ActivityType(
        id=type_id, name=request.name.strip(), active=request.active, band_kinds=row.band_kinds
    )


SELECT = """
    select a.id, a.activity_type_id, t.name, a.day, a.start_time, a.duration_seconds, a.notes,
           a.source, a.band, a.band_id, a.ongoing
    from training.training_activity a join training.training_activity_type t on t.id = a.activity_type_id
"""

DEFAULT_START = time(18, 30)

ANNOUNCED = text("""
    select id from training.training_activity
    where activity_type_id = cast(:type as uuid) and day = :day
      and source = 'received' and band_id is null and not ongoing
    order by abs(extract(epoch from (start_time - cast(:start as time))))
    limit 1
""")


def _row(row) -> Activity:
    return Activity(
        id=str(row.id),
        activity_type_id=str(row.activity_type_id),
        name=row.name,
        day=row.day,
        start_time=row.start_time,
        duration_seconds=row.duration_seconds,
        notes=row.notes,
        source=row.source,
        band=row.band,
        from_band=row.band_id is not None,
        ongoing=row.ongoing,
    )


async def between(connection: AsyncConnection, first: date, last: date) -> list[Activity]:
    rows = await connection.execute(
        text(
            SELECT + " where a.day between :first and :last "
            "order by a.day desc, a.start_time desc, a.created_at desc"
        ),
        {"first": first, "last": last},
    )
    return [_row(row) for row in rows]


async def log(connection: AsyncConnection, request: ActivityIn, *, source: str = "app") -> Activity:
    exists = await connection.scalar(
        text("select 1 from training.training_activity_type where id = cast(:id as uuid)"),
        {"id": request.activity_type_id},
    )
    if not exists:
        raise Conflict("that activity does not exist; create it first")
    if source == "app":
        start = request.start_time or DEFAULT_START
        twin = await _twin(
            connection,
            request.activity_type_id,
            request.day,
            start,
            request.duration_seconds,
            band=True,
        )
        if twin is not None:
            if request.notes and request.notes.strip():
                await connection.execute(
                    text(
                        "update training.training_activity set notes = :notes "
                        "where id = cast(:id as uuid)"
                    ),
                    {"notes": request.notes.strip(), "id": twin},
                )
            return await one(connection, twin)
        announced = await connection.scalar(
            ANNOUNCED, {"type": request.activity_type_id, "day": request.day, "start": start}
        )
        if announced is not None:
            await connection.execute(
                text(
                    "update training.training_activity set start_time = :start, "
                    "duration_seconds = coalesce(:duration, duration_seconds), "
                    "notes = coalesce(:notes, notes) where id = :id"
                ),
                {
                    "start": start,
                    "duration": request.duration_seconds,
                    "notes": (request.notes or "").strip() or None,
                    "id": announced,
                },
            )
            activity = await one(connection, str(announced))
            await agenda.activity_changed(connection, activity)
            return activity
    activity_id = await connection.scalar(
        text(
            "insert into training.training_activity "
            "(activity_type_id, day, start_time, duration_seconds, notes, source) "
            "values (cast(:type as uuid), :day, :start, :duration, :notes, :source) returning id"
        ),
        {
            "type": request.activity_type_id,
            "day": request.day,
            "start": request.start_time or DEFAULT_START,
            "duration": request.duration_seconds,
            "notes": (request.notes or "").strip() or None,
            "source": source,
        },
    )
    activity = _row(
        (await connection.execute(text(SELECT + " where a.id = :id"), {"id": activity_id})).one()
    )
    await enqueue(
        connection,
        "training.activity_logged",
        datetime.now(UTC),
        {
            "activity_id": activity.id,
            "name": activity.name,
            "day": activity.day,
            "duration_seconds": activity.duration_seconds,
        },
        f"training:activity:{activity.id}:logged",
    )
    await agenda.activity_changed(connection, activity)
    return activity


async def one(connection: AsyncConnection, activity_id: str) -> Activity:
    found = (
        await connection.execute(
            text(SELECT + " where a.id = cast(:id as uuid)"), {"id": activity_id}
        )
    ).one_or_none()
    if found is None:
        raise NotFound(activity_id)
    return _row(found)


def _minute(moment: datetime) -> time:
    return moment.astimezone(zone()).time().replace(second=0, microsecond=0, tzinfo=None)


async def start_now(
    connection: AsyncConnection, activity_type_id: str, now: datetime | None = None
) -> Activity:
    now = (now or datetime.now(UTC)).astimezone(zone())
    exists = await connection.scalar(
        text("select 1 from training.training_activity_type where id = cast(:id as uuid)"),
        {"id": activity_type_id},
    )
    if not exists:
        raise Conflict("that activity does not exist; create it first")
    activity_id = await connection.scalar(
        text(
            "insert into training.training_activity "
            "(activity_type_id, day, start_time, ongoing, source) "
            "values (cast(:type as uuid), :day, :start, true, 'app') returning id"
        ),
        {"type": activity_type_id, "day": now.date(), "start": _minute(now)},
    )
    activity = await one(connection, str(activity_id))
    await agenda.activity_changed(connection, activity)
    return activity


async def finish(
    connection: AsyncConnection, activity_id: str, now: datetime | None = None
) -> Activity:
    found = await one(connection, activity_id)
    if not found.ongoing:
        return found
    now = (now or datetime.now(UTC)).astimezone(zone())
    began = datetime.combine(found.day, found.start_time, zone())
    seconds = max(0, min(86400, int((now - began).total_seconds())))
    await connection.execute(
        text(
            "update training.training_activity set ongoing = false, duration_seconds = :seconds "
            "where id = cast(:id as uuid)"
        ),
        {"seconds": seconds, "id": activity_id},
    )
    activity = await one(connection, activity_id)
    await agenda.activity_changed(connection, activity, stamp=now)
    return activity


async def ongoing(connection: AsyncConnection) -> list[Activity]:
    rows = await connection.execute(
        text(SELECT + " where a.ongoing order by a.day desc, a.start_time desc")
    )
    return [_row(row) for row in rows]


async def remove(connection: AsyncConnection, activity_id: str) -> None:
    found = (
        await connection.execute(
            text(SELECT + " where a.id = cast(:id as uuid)"), {"id": activity_id}
        )
    ).one_or_none()
    if found is None:
        raise NotFound(activity_id)
    await connection.execute(
        text("delete from training.training_activity where id = cast(:id as uuid)"),
        {"id": activity_id},
    )
    await agenda.activity_removed(connection, _row(found))
    await enqueue(
        connection,
        "training.activity_removed",
        datetime.now(UTC),
        {"activity_id": activity_id},
        f"training:activity:{activity_id}:removed",
    )


RECEIVED = text(f"""
    select distinct on (payload->'{contracts.ACTIVITY}'->>'id')
        payload->'{contracts.ACTIVITY}' as activity
    from training.events e
    where module <> 'training' and payload ? '{contracts.ACTIVITY}'
      and not exists (
          select 1 from training.training_activity_received r
          where r.origin_id = e.payload->'{contracts.ACTIVITY}'->>'id'
      )
    order by payload->'{contracts.ACTIVITY}'->>'id', ts desc, ingested_at desc
""")


SAME_DAY = text("""
    select 1 from training.training_activity
    where activity_type_id = cast(:type as uuid) and day = :day
    limit 1
""")


async def receive(connection: AsyncConnection) -> int:
    added = 0
    for row in (await connection.execute(RECEIVED)).all():
        found = row.activity
        await connection.execute(
            text("insert into training.training_activity_received (origin_id) values (:id)"),
            {"id": found["id"]},
        )
        if found.get("removed"):
            continue
        try:
            start = datetime.fromisoformat(found["start"]).astimezone(ZoneInfo(found["tz"]))
            name = str(found["name"]).strip()[:60]
        except (KeyError, ValueError, TypeError):
            continue
        kind = await create_type(connection, ActivityTypeIn(name=name))
        if await connection.scalar(SAME_DAY, {"type": kind.id, "day": start.date()}):
            continue
        minutes = found.get("minutes")
        await log(
            connection,
            ActivityIn(
                activity_type_id=kind.id,
                day=start.date(),
                start_time=start.time().replace(second=0, microsecond=0),
                duration_seconds=None if minutes is None else int(minutes) * 60,
            ),
            source="received",
        )
        added += 1
    return added


EXERCISES = text("""
    select distinct on (payload->>'id') payload
    from training.events e
    where type = 'health.exercise'
      and not exists (
          select 1 from training.training_activity_received r where r.origin_id = e.payload->>'id'
      )
    order by payload->>'id', ingested_at desc, ts desc
""")

STRENGTH = frozenset(
    {
        "STRENGTH_TRAINING",
        "WEIGHTLIFTING",
        "WEIGHTS",
        "FREE_WEIGHTS",
        "WEIGHT_MACHINES",
        "POWERLIFTING",
        "FUNCTIONAL_STRENGTH_TRAINING",
        "BODY_WEIGHT",
        "CALISTHENICS",
        "RESISTANCE_BANDS",
    }
)

WALKS = frozenset({"WALKING", "POWER_WALKING", "WALK"})

BIKES = frozenset({"BIKING", "OUTDOOR_BIKE", "MOUNTAIN_BIKE", "STATIONARY_BIKE", "SPINNING"})

GENERIC = frozenset({"SPORT", "OTHER", "WORKOUT", "UNKNOWN"})

NAMES = {
    "RUNNING": "Running",
    "TRAIL_RUN": "Running",
    "TREADMILL": "Treadmill",
    "BIKING": "Cycling",
    "OUTDOOR_BIKE": "Cycling",
    "MOUNTAIN_BIKE": "Cycling",
    "STATIONARY_BIKE": "Indoor cycling",
    "SPINNING": "Indoor cycling",
    "SWIMMING": "Swimming",
    "SWIMMING_POOL": "Swimming",
    "SWIMMING_OPEN_WATER": "Swimming",
    "HIKING": "Hiking",
    "YOGA": "Yoga",
    "PILATES": "Pilates",
    "PADEL": "Padel",
    "TENNIS": "Tennis",
    "CLIMBING": "Climbing",
    "ROCK_CLIMBING": "Climbing",
    "INDOOR_CLIMBING": "Climbing",
    "ELLIPTICAL": "Elliptical",
    "ROWING_MACHINE": "Rowing",
    "HIIT": "HIIT",
    "SOCCER": "Football",
}

ALSO = {
    "Indoor cycling": ("Cycling", "Spinning"),
    "Cycling": ("Indoor cycling",),
    "Swimming": ("Swim", "Pool"),
}

NEAR = timedelta(minutes=60)


def folded(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name.strip().lower())
    return " ".join("".join(c for c in plain if not unicodedata.combining(c)).split())


def measured(found: dict) -> dict[str, Any]:
    kept: dict[str, Any] = {}
    for key in (
        "kcal",
        "distance_km",
        "heart_rate_avg",
        "active_zone_min",
        "elevation_gain_m",
        "cadence_spm",
        "swim_lengths",
        "hr_zone_min",
        "steps",
    ):
        if found.get(key) is not None:
            kept[key] = found[key]
    beats = [one["bpm"] for one in found.get("heart") or [] if one.get("bpm") is not None]
    if beats:
        kept["heart_rate_max"] = max(beats)
    return kept


async def type_for(
    connection: AsyncConnection, kind: str, name: str, *, create: bool = True
) -> ActivityType | None:
    known = await types(connection)
    for one in known:
        if kind in one.band_kinds:
            return one
    names = [name, *ALSO.get(name, ())]
    by_name = {folded(one.name): one for one in known}
    for candidate in names:
        if (found := by_name.get(folded(candidate))) is not None:
            return found
    if not create:
        return None
    return await create_type(connection, ActivityTypeIn(name=name))


TWINS = text("""
    select a.id, a.day, a.start_time, a.duration_seconds
    from training.training_activity a
    where (cast(:type as uuid) is null or a.activity_type_id = cast(:type as uuid))
      and a.day between :first and :last and (a.band_id is not null) = :band
""")


async def _twin(
    connection: AsyncConnection,
    type_id: str | None,
    day: date,
    start: time,
    seconds: int | None,
    *,
    band: bool,
) -> str | None:
    began = datetime.combine(day, start, zone())
    ended = began + timedelta(seconds=seconds or 3600)
    rows = (
        await connection.execute(
            TWINS,
            {
                "type": type_id,
                "first": day - timedelta(days=1),
                "last": day + timedelta(days=1),
                "band": band,
            },
        )
    ).all()
    best = None
    for row in rows:
        other = datetime.combine(row.day, row.start_time, zone())
        other_end = other + timedelta(seconds=row.duration_seconds or 3600)
        gap = abs(other - began)
        same = (other < ended and began < other_end) or gap < NEAR
        if same and (best is None or gap < best[0]):
            best = (gap, str(row.id))
    return best[1] if best else None


SESSIONS_AROUND = text("""
    select id from training.training_session
    where band_id is null and ended_at is not null
      and started_at < :end and ended_at > :start
    order by abs(extract(epoch from (started_at - :start)))
    limit 1
""")

STRENGTH_WAIT = timedelta(days=3)


async def _seen(connection: AsyncConnection, origin: str) -> None:
    await connection.execute(
        text("insert into training.training_activity_received (origin_id) values (:id)"),
        {"id": origin},
    )


async def _strength(connection: AsyncConnection, found: dict, now: datetime) -> None:
    try:
        start = datetime.fromisoformat(found["start"])
        end = datetime.fromisoformat(found["end"])
    except (KeyError, ValueError, TypeError):
        await _seen(connection, found.get("id", ""))
        return
    session = await connection.scalar(SESSIONS_AROUND, {"start": start, "end": end})
    if session is None:
        if now - end > STRENGTH_WAIT:
            await _seen(connection, found["id"])
        return
    await connection.execute(
        text("update training.training_session set band_id = :band where id = :id"),
        {"band": found["id"], "id": session},
    )
    await _seen(connection, found["id"])
    await agenda.session_changed(connection, str(session), stamp=now)


async def receive_exercises(connection: AsyncConnection, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    touched = 0
    for row in (await connection.execute(EXERCISES)).all():
        found = row.payload
        kind = str(found.get("kind", ""))
        if kind in STRENGTH:
            await _strength(connection, found, now)
            continue
        await _seen(connection, found["id"])
        if kind in WALKS:
            continue
        try:
            start = datetime.fromisoformat(found["start"]).astimezone(zone())
            end = datetime.fromisoformat(found["end"]).astimezone(zone())
            name = (NAMES.get(kind) or str(found["name"]).strip())[:60]
        except (KeyError, ValueError, TypeError):
            continue
        at = start.time().replace(second=0, microsecond=0, tzinfo=None)
        seconds = round((end - start).total_seconds())
        if seconds <= 0 and found.get("minutes") is not None:
            seconds = round(float(found["minutes"]) * 60)
        seconds = max(0, min(86400, seconds))
        mine = None
        if kind in GENERIC and not any(kind in one.band_kinds for one in await types(connection)):
            mine = await _twin(connection, None, start.date(), at, seconds, band=False)
        if mine is None:
            kind_type = await type_for(connection, kind, name, create=kind in BIKES)
            if kind_type is not None:
                mine = await _twin(connection, kind_type.id, start.date(), at, seconds, band=False)
        if mine is None and kind not in BIKES:
            continue
        values = {
            "day": start.date(),
            "start": at,
            "duration": seconds,
            "band_id": found["id"],
            "band": json.dumps(measured(found)),
        }
        if mine is not None:
            await connection.execute(
                text(
                    "update training.training_activity set day = :day, start_time = :start, "
                    "duration_seconds = :duration, band_id = :band_id, "
                    "band = cast(:band as jsonb), ongoing = false where id = cast(:id as uuid)"
                ),
                {**values, "id": mine},
            )
            activity = await one(connection, mine)
            await agenda.activity_changed(connection, activity, stamp=now)
        else:
            activity_id = await connection.scalar(
                text(
                    "insert into training.training_activity (activity_type_id, day, start_time, "
                    "duration_seconds, band_id, band, source) values (cast(:type as uuid), :day, "
                    ":start, :duration, :band_id, cast(:band as jsonb), 'received') returning id"
                ),
                {**values, "type": kind_type.id},
            )
            activity = await one(connection, str(activity_id))
            await enqueue(
                connection,
                "training.activity_logged",
                datetime.now(UTC),
                {
                    "activity_id": activity.id,
                    "name": activity.name,
                    "day": activity.day,
                    "duration_seconds": activity.duration_seconds,
                },
                f"training:activity:{activity.id}:logged",
            )
            await agenda.activity_changed(connection, activity)
        touched += 1
    return touched


GENERIC_FROM_BAND = text(f"""
    select a.id, a.day, a.start_time, a.duration_seconds, a.band_id, a.band, a.notes
    from training.training_activity a
    where a.band_id is not null and exists (
        select 1 from training.events e
        where e.type = 'health.exercise' and e.payload->>'id' = a.band_id
          and e.payload->>'kind' in ({", ".join(f"'{one}'" for one in sorted(GENERIC))})
    )
""")

ANNOUNCED_AND_LOGGED = text("""
    select r.id from training.training_activity r
    where r.source = 'received' and r.band_id is null and exists (
        select 1 from training.training_activity a
        where a.id <> r.id and a.activity_type_id = r.activity_type_id and a.day = r.day
          and a.source = 'app'
    )
""")


async def _drop(connection: AsyncConnection, activity_id) -> None:
    found = await one(connection, str(activity_id))
    await connection.execute(
        text("delete from training.training_activity where id = cast(:id as uuid)"),
        {"id": str(activity_id)},
    )
    await agenda.activity_removed(connection, found)


async def join_twins(connection: AsyncConnection) -> int:
    joined = 0
    for row in (await connection.execute(GENERIC_FROM_BAND)).all():
        mine = await _twin(
            connection, None, row.day, row.start_time, row.duration_seconds, band=False
        )
        if mine is None:
            continue
        await _drop(connection, row.id)
        await connection.execute(
            text(
                "update training.training_activity set day = :day, start_time = :start, "
                "duration_seconds = :duration, band_id = :band_id, band = cast(:band as jsonb), "
                "notes = coalesce(notes, :notes), ongoing = false where id = cast(:id as uuid)"
            ),
            {
                "day": row.day,
                "start": row.start_time,
                "duration": row.duration_seconds,
                "band_id": row.band_id,
                "band": json.dumps(row.band),
                "notes": row.notes,
                "id": mine,
            },
        )
        await agenda.activity_changed(connection, await one(connection, mine))
        joined += 1
    for row in (await connection.execute(ANNOUNCED_AND_LOGGED)).all():
        await _drop(connection, row.id)
        joined += 1
    return joined


async def move(
    connection: AsyncConnection, activity_id: str, start: datetime, end: datetime
) -> Activity:
    found = (
        await connection.execute(
            text(SELECT + " where a.id = cast(:id as uuid) for update of a"), {"id": activity_id}
        )
    ).one_or_none()
    if found is None:
        raise NotFound(activity_id)
    local = start.astimezone(zone())
    seconds = int((end - start).total_seconds())
    if seconds < 0 or seconds > 86400:
        raise Conflict("an activity lasts between zero and one day")
    stays_open = found.duration_seconds is None and not found.ongoing and seconds == 3600
    duration = None if stays_open else seconds
    await connection.execute(
        text(
            "update training.training_activity set day = :day, start_time = :start, "
            "duration_seconds = :duration, ongoing = false where id = cast(:id as uuid)"
        ),
        {
            "day": local.date(),
            "start": local.time().replace(second=0, microsecond=0, tzinfo=None),
            "duration": duration,
            "id": activity_id,
        },
    )
    activity = _row(
        (
            await connection.execute(
                text(SELECT + " where a.id = cast(:id as uuid)"), {"id": activity_id}
            )
        ).one()
    )
    now = datetime.now(UTC)
    await enqueue(
        connection,
        "training.activity_moved",
        now,
        {
            "activity_id": activity.id,
            "day": activity.day,
            "start_time": activity.start_time,
            "duration_seconds": activity.duration_seconds,
        },
        f"training:activity:{activity.id}:moved:{now.isoformat()}",
    )
    await agenda.activity_changed(connection, activity, stamp=now)
    return activity
