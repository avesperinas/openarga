from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hub import credentials

TOKEN_KEY = "ingest_token"
MAX_ITEMS = 1000
MAX_SAMPLES = 50_000


class Denied(Exception):
    pass


def issue(user: UUID, connection_id: UUID) -> str:
    return f"{user.hex}.{connection_id.hex}.{secrets.token_urlsafe(32)}"


def claimed(authorization: str | None) -> tuple[UUID, UUID, str]:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token.count(".") != 2:
        raise Denied()
    user, connection_id, _secret = token.split(".")
    try:
        return UUID(hex=user), UUID(hex=connection_id), token
    except ValueError as error:
        raise Denied() from error


async def store(database: AsyncConnection, provider: str, user: UUID, connection_id: UUID) -> str:
    token = issue(user, connection_id)
    await credentials.store(database, provider, connection_id, TOKEN_KEY, token)
    return token


ROW = text("""
    select id, provider, label, status, paused
    from hub.hub_connection where id = :id
""")


async def verify(database: AsyncConnection, provider: str, connection_id: UUID, token: str) -> Any:
    row = (await database.execute(ROW, {"id": connection_id})).one_or_none()
    if row is None or row.provider != provider or row.paused or row.status != "active":
        raise Denied()
    stored = await credentials.use(database, provider, connection_id, TOKEN_KEY)
    if stored is None or not hmac.compare_digest(stored.encode(), token.encode()):
        raise Denied()
    return row


METRICS: dict[str, tuple[float, float]] = {
    "heart_rate_min": (20, 250),
    "heart_rate_avg": (20, 250),
    "heart_rate_max": (20, 250),
    "resting_heart_rate": (20, 200),
    "walking_heart_rate": (20, 250),
    "hrv_ms": (0, 500),
    "vo2max": (5, 100),
    "high_heart_rate_events": (0, 100),
    "low_heart_rate_events": (0, 100),
    "active_kcal": (0, 20_000),
    "basal_kcal": (0, 10_000),
    "distance_km": (0, 500),
    "cycling_km": (0, 1_000),
    "flights": (0, 1_000),
    "exercise_min": (0, 1_440),
    "stand_min": (0, 1_440),
    "stand_hours": (0, 24),
    "physical_effort": (0, 30),
    "move_goal_kcal": (0, 10_000),
    "exercise_goal_min": (0, 1_440),
    "stand_goal_hours": (0, 24),
    "sleep_min": (0, 1_440),
    "in_bed_min": (0, 1_440),
    "walking_speed_kmh": (0, 20),
    "step_length_cm": (0, 250),
    "double_support_pct": (0, 100),
    "asymmetry_pct": (0, 100),
    "steadiness_pct": (0, 100),
    "six_minute_walk_m": (0, 2_000),
    "stair_up_ms": (0, 10),
    "stair_down_ms": (0, 10),
    "respiratory_rate": (0, 100),
    "mindful_min": (0, 1_440),
    "headphone_db": (0, 150),
    "environment_db": (0, 150),
    "headphone_noise_events": (0, 100),
    "environment_noise_events": (0, 1_000),
}

BLOOD_TYPES = ("A+", "A-", "B+", "B-", "AB+", "AB-", "0+", "0-")


class StepsDay(BaseModel):
    date: date
    steps: int = Field(ge=0, le=300_000)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blood_type: Literal[BLOOD_TYPES] | None = None  # type: ignore[valid-type]
    sex: Literal["female", "male", "other"] | None = None
    birth_date: date | None = None
    height_cm: float | None = Field(default=None, ge=50, le=260)
    cardio_medications: str | None = Field(default=None, max_length=120)


@dataclass(frozen=True)
class Received:
    operation: str
    events: list[dict[str, Any]]


def number(key: str, raw: Any) -> float:
    if isinstance(raw, str):
        raw = raw.strip().replace(",", ".")
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{key}: no es un número") from error
    low, high = METRICS[key]
    if not low <= value <= high:
        raise ValueError(f"{key}: {value} fuera de [{low}, {high}]")
    return round(value, 2)


def digest(values: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]


def quantity(raw: Any) -> float:
    if isinstance(raw, str):
        raw = raw.strip().replace(" ", "").replace("\u00a0", "")
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", raw):
            return float(re.sub(r"[.,]", "", raw))
        raw = raw.replace(",", ".")
    return float(raw)


def count(raw: Any) -> Any:
    try:
        return round(quantity(raw))
    except (TypeError, ValueError):
        return raw


def listed(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and "\n" in raw.strip():
        return [line.strip() for line in raw.strip().splitlines() if line.strip()]
    return [raw]


def several(item: Any) -> list[Any]:
    if not isinstance(item, dict) or "date" not in item:
        return [item]
    dates = listed(item["date"])
    if len(dates) == 1:
        return [{**item, "date": dates[0]}]
    latest = max(range(len(dates)), key=lambda at: str(dates[at]))
    days: list[dict[str, Any]] = [{"date": one} for one in dates]
    for key, raw in item.items():
        if key == "date":
            continue
        values = listed(raw)
        if len(values) == len(dates):
            for day, value in zip(days, values, strict=True):
                day[key] = value
        elif len(values) == 1:
            days[latest][key] = values[0]
        else:
            raise ValueError(f"{key}: {len(values)} valores para {len(dates)} fechas")
    return [day for day in days if set(day) != {"date"}]


PRIORITY = ("watch", "iphone")
SAMPLE_KEYS = ("start", "end", "steps", "source")


@dataclass(frozen=True)
class Sample:
    start: datetime
    end: datetime
    steps: float
    rank: int


def rank_of(source: str) -> int:
    name = source.lower()
    return next((at for at, kind in enumerate(PRIORITY) if kind in name), len(PRIORITY))


def moment(key: str, raw: Any) -> datetime:
    try:
        found = datetime.fromisoformat(str(raw).strip())
    except ValueError as error:
        raise ValueError(f"{key}: {raw!r} no es una fecha ISO 8601") from error
    if found.tzinfo is None:
        raise ValueError(f"{key}: {raw!r} sin zona horaria")
    return found


def samples_of(item: dict[str, Any]) -> list[Sample]:
    columns = {key: listed(item.get(key)) for key in SAMPLE_KEYS}
    lengths = {len(values) for values in columns.values()}
    if len(lengths) != 1:
        raise ValueError(f"start, end, steps y source no casan: {sorted(lengths)} valores")
    found = []
    for start, end, steps, source in zip(*columns.values(), strict=True):
        try:
            value = quantity(steps)
        except (TypeError, ValueError) as error:
            raise ValueError(f"steps: {steps!r} no es un número") from error
        sample = Sample(moment("start", start), moment("end", end), value, rank_of(str(source)))
        if sample.end < sample.start or not 0 <= value <= 100_000:
            raise ValueError(f"muestra imposible: {start} – {end}, {steps} pasos")
        found.append(sample)
    if len(found) > MAX_SAMPLES:
        raise ValueError(f"más de {MAX_SAMPLES} muestras")
    return found


Span = tuple[datetime, datetime]


def merged(spans: list[Span]) -> list[Span]:
    found: list[Span] = []
    for low, high in sorted(spans):
        if found and low <= found[-1][1]:
            found[-1] = (found[-1][0], max(found[-1][1], high))
        else:
            found.append((low, high))
    return found


def uncovered(start: datetime, end: datetime, covered: list[Span]) -> list[Span]:
    pieces = []
    cursor = start
    for low, high in covered[max(bisect_right(covered, start, key=first) - 1, 0) :]:
        if low >= end:
            break
        if high <= cursor:
            continue
        if low > cursor:
            pieces.append((cursor, low))
        cursor = high
        if cursor >= end:
            break
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def first(span: Span) -> datetime:
    return span[0]


def by_day(start: datetime, end: datetime, steps: float) -> dict[date, float]:
    if start == end:
        return {start.date(): steps}
    total = (end - start).total_seconds()
    found: dict[date, float] = {}
    cursor = start
    while cursor < end:
        midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
        stop = min(end, midnight.replace(tzinfo=cursor.tzinfo))
        found[cursor.date()] = (
            found.get(cursor.date(), 0) + steps * (stop - cursor).total_seconds() / total
        )
        cursor = stop
    return found


def as_health_counts(samples: list[Sample]) -> dict[date, float]:
    days: dict[date, float] = {}
    covered: list[Span] = []
    for rank in sorted({one.rank for one in samples}):
        level = [one for one in samples if one.rank == rank]
        for one in level:
            if one.start == one.end:
                at = bisect_right(covered, one.start, key=first) - 1
                inside = at >= 0 and covered[at][1] > one.start
                pieces = [] if inside else [(one.start, one.end, one.steps)]
            else:
                length = (one.end - one.start).total_seconds()
                pieces = [
                    (a, b, one.steps * (b - a).total_seconds() / length)
                    for a, b in uncovered(one.start, one.end, covered)
                ]
            for a, b, steps in pieces:
                for day, value in by_day(a, b, steps).items():
                    days[day] = days.get(day, 0) + value
        covered = merged(covered + [(one.start, one.end) for one in level if one.start < one.end])
    return days


HOURLY_KEYS = ("watch_start", "watch_steps", "phone_start", "phone_steps")


def hours_of(item: dict[str, Any], source: str) -> dict[datetime, float]:
    starts = [one for one in listed(item.get(f"{source}_start", "")) if str(one).strip()]
    steps = [one for one in listed(item.get(f"{source}_steps", "")) if str(one).strip()]
    if len(starts) != len(steps):
        raise ValueError(f"{source}: {len(starts)} horas y {len(steps)} valores")
    found: dict[datetime, float] = {}
    for start, value in zip(starts, steps, strict=True):
        try:
            amount = quantity(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{source}_steps: {value!r} no es un número") from error
        if not 0 <= amount <= 100_000:
            raise ValueError(f"{source}_steps: {value!r} fuera de rango")
        hour = moment(f"{source}_start", start).replace(minute=0, second=0, microsecond=0)
        found[hour] = found.get(hour, 0) + amount
    return found


def by_hours(item: dict[str, Any]) -> dict[date, float]:
    watch, phone = hours_of(item, "watch"), hours_of(item, "phone")
    days: dict[date, float] = {}
    for hour in set(watch) | set(phone):
        days[hour.date()] = days.get(hour.date(), 0) + max(watch.get(hour, 0), phone.get(hour, 0))
    return days


def from_samples(item: dict[str, Any]) -> list[dict[str, Any]]:
    hourly = any(key in item for key in HOURLY_KEYS)
    counts = by_hours(item) if hourly else as_health_counts(samples_of(item))
    if not counts:
        raise ValueError("no trae muestras")
    days = sorted(counts)
    if len(days) > 1:
        days = days[1:]
    found: list[dict[str, Any]] = [{"date": day, "steps": round(counts[day])} for day in days]
    for key, raw in item.items():
        if key in (HOURLY_KEYS if hourly else SAMPLE_KEYS):
            continue
        values = listed(raw)
        if len(values) != 1:
            raise ValueError(f"{key}: con muestras, un solo valor del día más reciente")
        found[-1][key] = values[0]
    return found


def one_day(item: Any, today: date) -> list[dict[str, Any]]:
    if not isinstance(item, dict) or "date" not in item:
        raise ValueError("cada día necesita su `date`")
    unknown = sorted(set(item) - {"date", "steps"} - set(METRICS))
    if unknown:
        raise ValueError(f"no se conoce: {', '.join(unknown)}")
    day = StepsDay.model_validate({"date": item["date"], "steps": 0}).date
    if day > today + timedelta(days=1):
        raise ValueError(f"días en el futuro: {day.isoformat()}")
    metrics = {key: number(key, raw) for key, raw in item.items() if key in METRICS and raw != ""}
    if "steps" not in item and not metrics:
        raise ValueError(f"{day.isoformat()}: no trae nada")
    events = []
    ts = f"{day.isoformat()}T12:00:00+00:00"
    if "steps" in item:
        steps = StepsDay.model_validate({"date": day, "steps": count(item["steps"])}).steps
        events.append(
            {
                "ts": ts,
                "type": "health.steps",
                "payload": {"date": day.isoformat(), "steps": steps},
                "dedup_hash": f"steps:{day.isoformat()}:{steps}",
            }
        )
    if metrics:
        events.append(
            {
                "ts": ts,
                "type": "health.daily",
                "payload": {"date": day.isoformat(), "metrics": metrics},
                "dedup_hash": f"daily:{day.isoformat()}:{digest(metrics)}",
            }
        )
    return events


def profile(values: Any, today: date) -> dict[str, Any]:
    found = Profile.model_validate(values).model_dump(mode="json", exclude_none=True)
    if not found:
        raise ValueError("la ficha llega vacía")
    return {
        "ts": f"{today.isoformat()}T12:00:00+00:00",
        "type": "health.profile",
        "payload": found,
        "dedup_hash": f"profile:{digest(found)}",
    }


def apple_health(body: Any, today: date) -> Received:
    events: list[dict[str, Any]] = []
    if isinstance(body, dict) and set(body) <= {"days", "profile"} and body:
        if "profile" in body:
            events.append(profile(body["profile"], today))
        body = body.get("days", [])
        if not isinstance(body, list) or (not body and not events):
            raise ValueError(f"se espera una lista de 1 a {MAX_ITEMS} días")
    elif isinstance(body, dict):
        body = [body]
    if isinstance(body, list):
        body = [
            day
            for item in body
            for day in (
                from_samples(item)
                if isinstance(item, dict) and {"start", *HOURLY_KEYS} & set(item)
                else several(item)
            )
        ]
    if not isinstance(body, list) or len(body) > MAX_ITEMS or (not body and not events):
        raise ValueError(f"se espera una lista de 1 a {MAX_ITEMS} días")
    for item in body:
        events.extend(one_day(item, today))
    return Received("health", events)


RECEIVERS = {"apple-health": ("apple_health", apple_health)}
