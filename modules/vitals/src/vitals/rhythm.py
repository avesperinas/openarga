from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

LATEST = text("""
    select distinct on (payload->>'id') payload
    from vitals.events
    where type = :type
    order by payload->>'id', ingested_at desc, ts desc
""")

RESULTS = {
    "normal_sinus_rhythm": "Ritmo sinusal normal",
    "atrial_fibrillation": "Fibrilación auricular",
    "inconclusive": "No concluyente",
    "inconclusive_high_heart_rate": "No concluyente: vitals por encima de 120",
    "inconclusive_low_heart_rate": "No concluyente: vitals por debajo de 50",
    "unreadable": "No se pudo leer",
    "not_analyzed": "Sin analizar",
}

TRACE_POINTS = 1500


class Ecg(BaseModel):
    id: str
    start: datetime
    end: datetime
    result: str | None
    result_text: str | None
    heart_rate_avg: float | None
    seconds: float | None
    device: str | None


class EcgTrace(Ecg):
    step_seconds: float | None
    millivolts: list[float]


class Irn(BaseModel):
    id: str
    start: datetime
    end: datetime
    windows: int
    positive_windows: int
    device: str | None


class Device(BaseModel):
    id: str
    name: str
    kind: str
    battery_pct: int | None
    battery: str | None
    last_sync: datetime | None


RECENT = text("""
    select distinct on (payload->>'id') payload
    from vitals.events
    where type = 'health.device' and ingested_at >= :arrived
    order by payload->>'id', ingested_at desc, ts desc
""")
RECENT_DAYS = 30


async def latest(connection: AsyncConnection, kind: str) -> list[dict]:
    return [row.payload for row in (await connection.execute(LATEST, {"type": kind})).all()]


async def recent_devices(connection: AsyncConnection) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    found = [row.payload for row in (await connection.execute(RECENT, {"arrived": since})).all()]
    return found or await latest(connection, "health.device")


def seconds(found: dict) -> float | None:
    hz, samples = found.get("sampling_hz"), found.get("samples") or []
    return round(len(samples) / hz, 1) if hz and samples else None


def ecg(found: dict) -> Ecg:
    return Ecg(
        id=found["id"],
        start=found["start"],
        end=found["end"],
        result=found.get("result"),
        result_text=RESULTS.get(found.get("result") or ""),
        heart_rate_avg=found.get("heart_rate_avg"),
        seconds=seconds(found),
        device=found.get("device"),
    )


async def ecgs(connection: AsyncConnection) -> list[Ecg]:
    found = [ecg(one) for one in await latest(connection, "health.ecg")]
    return sorted(found, key=lambda one: one.start, reverse=True)


def trace(found: dict) -> EcgTrace:
    samples = found.get("samples") or []
    scale = found.get("millivolts_scale") or 1
    every = max(1, -(-len(samples) // TRACE_POINTS))
    hz = found.get("sampling_hz")
    return EcgTrace(
        **ecg(found).model_dump(),
        step_seconds=round(every / hz, 4) if hz else None,
        millivolts=[round(one / scale, 3) for one in samples[::every]],
    )


async def ecg_trace(connection: AsyncConnection, ecg_id: str) -> EcgTrace | None:
    found = next(
        (one for one in await latest(connection, "health.ecg") if one["id"] == ecg_id), None
    )
    return trace(found) if found else None


async def irns(connection: AsyncConnection) -> list[Irn]:
    found = [
        Irn(
            id=one["id"],
            start=one["start"],
            end=one["end"],
            windows=one.get("windows", 0),
            positive_windows=one.get("positive_windows", 0),
            device=one.get("device"),
        )
        for one in await latest(connection, "health.irn")
    ]
    return sorted(found, key=lambda one: one.start, reverse=True)


async def devices(connection: AsyncConnection) -> list[Device]:
    found = [
        Device(
            id=one["id"],
            name=one["name"],
            kind=one.get("kind", "other"),
            battery_pct=one.get("battery_pct"),
            battery=one.get("battery"),
            last_sync=one.get("last_sync"),
        )
        for one in await recent_devices(connection)
    ]
    return sorted(
        found, key=lambda one: one.last_sync.timestamp() if one.last_sync else 0, reverse=True
    )
