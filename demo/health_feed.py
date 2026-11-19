from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.demo import Persona

DAYS = 18 * 30
HEART_DAYS = 14
SOURCE = "google_health"

INSERT = text("""
    insert into kernel.events (ts, ingested_at, module, source, type, payload, dedup_hash, user_id)
    values (:ts, :received, 'hub', :source, :type, cast(:payload as jsonb), :dedup, :user)
    on conflict do nothing
""")

BANDS = {
    "alex": ("Pulse Band 4", "tracker"),
    "sam": ("Orbit Watch S", "tracker"),
}
SCALES = {"alex": "Lumen Scale", "sam": "Lumen Scale"}


def _noise(persona: Persona, key: str) -> float:
    digest = hashlib.sha256(f"{persona.key}:{key}".encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


def _spread(persona: Persona, key: str, low: float, high: float) -> float:
    return low + (high - low) * _noise(persona, key)


def _progress(back: int) -> float:
    return 1 - back / DAYS


def _steps(persona: Persona, day: date, back: int) -> int | None:
    if _noise(persona, f"gap-{back}") < 0.025:
        return None
    alex = persona.key == "alex"
    base = 7600 + 1900 * _progress(back) if alex else 8600 + 900 * _progress(back)
    weekend = day.weekday() >= 5
    if weekend:
        base *= 1.35 if _noise(persona, f"hike-{back}") > 0.55 else 0.8
    if alex and day.weekday() in (1, 3):
        base += 2300
    if not alex and day.weekday() in (0, 2, 4):
        base += 1500
    return max(1200, round(base * _spread(persona, f"steps-{back}", 0.72, 1.28)))


def _metrics(persona: Persona, day: date, back: int, steps: int) -> dict[str, float]:
    alex = persona.key == "alex"
    fit = _progress(back)
    resting = (63 - 6 * fit) if alex else (60 - 3 * fit)
    resting += _spread(persona, f"rhr-{back}", -1.6, 1.6) + 0.8 * math.sin(back / 21)
    hrv = (38 + 10 * fit) if alex else (52 + 6 * fit)
    hrv += _spread(persona, f"hrv-{back}", -5, 5)
    active = steps * (0.043 if alex else 0.037)
    moderate = max(4.0, steps / 380 + _spread(persona, f"mod-{back}", -6, 8))
    vigorous = max(0.0, _spread(persona, f"vig-{back}", -8, 14) + (6 if alex else 3))
    metrics = {
        "resting_heart_rate": round(resting, 1),
        "sleep_heart_rate": round(resting - 4.5 + _spread(persona, f"shr-{back}", -1, 1), 1),
        "hrv_ms": round(hrv, 1),
        "hrv_deep_ms": round(hrv + 7, 1),
        "vo2max": round((42 + 4 * fit if alex else 38 + 2.5 * fit) + 0.4 * math.sin(back / 30), 1),
        "active_kcal": round(active, 1),
        "basal_kcal": 1780.0 if alex else 1420.0,
        "distance_km": round(steps * 0.00074, 2),
        "flights": float(round(steps / 1300 + _spread(persona, f"fl-{back}", 0, 5))),
        "light_active_min": round(steps / 52 + _spread(persona, f"lam-{back}", 0, 25), 0),
        "moderate_active_min": round(moderate, 0),
        "vigorous_active_min": round(vigorous, 0),
        "active_zone_min": round(moderate * 0.6 + vigorous * 2, 0),
        "sedentary_min": round(1440 - 480 - steps / 40 - _spread(persona, f"sed-{back}", 60, 240)),
        "hr_zone_light_min": round(steps / 90, 0),
        "hr_zone_moderate_min": round(moderate * 0.7, 0),
        "hr_zone_vigorous_min": round(vigorous * 0.8, 0),
        "hr_zone_peak_min": round(vigorous * 0.15, 0),
        "respiratory_rate": round(_spread(persona, f"rr-{back}", 13.4, 15.2), 1),
        "spo2_pct": round(_spread(persona, f"spo-{back}", 95.4, 98.2), 1),
        "spo2_min_pct": round(_spread(persona, f"spo2-{back}", 90.5, 94.5), 1),
        "spo2_max_pct": 99.0,
        "skin_temp_delta_c": round(_spread(persona, f"skin-{back}", -0.6, 0.6), 2),
    }
    return {key: float(value) for key, value in metrics.items()}


def _night(persona: Persona, day: date, back: int) -> dict[str, Any] | None:
    if _noise(persona, f"nosleep-{back}") < 0.02:
        return None
    alex = persona.key == "alex"
    weekend = day.weekday() in (5, 6)
    asleep = (
        (405 if alex else 440)
        + (35 if weekend else 0)
        + _spread(persona, f"asleep-{back}", -55, 50)
        + 15 * _progress(back)
    )
    if day.weekday() == 0 and not alex:
        asleep -= 40
    asleep = round(asleep)
    awake = round(_spread(persona, f"awake-{back}", 18, 52))
    fall = round(_spread(persona, f"fall-{back}", 5, 22))
    deep = round(asleep * _spread(persona, f"deep-{back}", 0.14, 0.2))
    rem = round(asleep * _spread(persona, f"rem-{back}", 0.18, 0.25))
    light = asleep - deep - rem
    bed_hour = 23.0 + _spread(persona, f"bed-{back}", -0.4, 0.9) + (0.7 if weekend else 0)
    start = datetime.combine(day - timedelta(days=1), time(0, 0)) + timedelta(hours=bed_hour)
    end = start + timedelta(minutes=asleep + awake + fall)
    stamp = "%Y-%m-%dT%H:%M:%S+01:00"
    order = (("light", 0.18), ("deep", 0.2), ("light", 0.14), ("rem", 0.1), ("deep", 0.08))
    order += (("light", 0.14), ("rem", 0.16))
    segments = []
    cursor = start
    total = (end - start).total_seconds()
    for stage, share in order:
        following = min(end, cursor + timedelta(seconds=total * share))
        segments.append(
            {"start": cursor.strftime(stamp), "end": following.strftime(stamp), "stage": stage}
        )
        cursor = following
    return {
        "id": f"night-{day.isoformat()}",
        "date": day.isoformat(),
        "start": start.strftime(stamp),
        "end": end.strftime(stamp),
        "minutes_asleep": asleep,
        "minutes_awake": awake,
        "minutes_to_fall_asleep": fall,
        "minutes_in_bed": asleep + awake + fall,
        "main": True,
        "stages": {"deep": deep, "rem": rem, "light": light, "awake": awake},
        "segments": segments,
        "awakenings": round(_spread(persona, f"wake-{back}", 1, 7)),
    }


def _heart(persona: Persona, day: date, back: int, upto: int) -> dict[str, Any]:
    buckets = []
    resting = 58 + _spread(persona, f"hr-base-{back}", -3, 3)
    for minute in range(0, upto, 5):
        hour = minute / 60
        asleep = hour < 6.5
        beat = resting - (6 if asleep else 0) + 14 * math.sin(hour / 24 * math.pi * 2 - 1.2) ** 2
        walking = 8 <= hour < 9 or 13.5 <= hour < 14.2 or 18 <= hour < 19.3
        beat += 28 * _noise(persona, f"w-{back}-{minute}") if walking else 0
        beat += _spread(persona, f"b-{back}-{minute}", -2.5, 2.5)
        steps = round(_noise(persona, f"s-{back}-{minute}") * 260) if walking else None
        buckets.append(
            {
                "minute": minute,
                "min": round(beat - 4, 1),
                "avg": round(beat, 1),
                "max": round(beat + 6 + (12 if walking else 0), 1),
                **({"steps": steps} if steps is not None else {}),
            }
        )
    return {"date": day.isoformat(), "step": 5, "buckets": buckets}


EXERCISES = {
    "alex": (
        (1, 3, "RUNNING", "Run", 18 * 60 + 30, 42, 9.4),
        (3, 5, "BIKING", "Bike ride", 10 * 60, 95, 31.0),
        (6, 6, "HIKING", "Hike", 9 * 60 + 30, 190, 13.5),
    ),
    "sam": (
        (0, 4, "YOGA", "Yoga", 19 * 60, 55, 0.0),
        (2, 3, "SWIMMING", "Swim", 7 * 60 + 30, 40, 1.4),
        (5, 6, "WALKING", "Walk", 11 * 60, 70, 5.6),
    ),
}


def _exercises(persona: Persona, day: date, back: int) -> list[dict[str, Any]]:
    found = []
    for weekday, every, kind, name, minute, length, distance in EXERCISES[persona.key]:
        if day.weekday() != weekday or (back // 7) % every not in (0, 1):
            continue
        if _noise(persona, f"ex-{kind}-{back}") < 0.18:
            continue
        stretch = _spread(persona, f"len-{back}", 0.85, 1.2)
        start = datetime.combine(day, time(minute // 60, minute % 60))
        stamp = "%Y-%m-%dT%H:%M:%S+01:00"
        minutes = round(length * stretch)
        exercise = {
            "id": f"band-{kind.lower()}-{day.isoformat()}",
            "kind": kind,
            "name": name,
            "start": start.strftime(stamp),
            "end": (start + timedelta(minutes=minutes)).strftime(stamp),
            "minutes": float(minutes),
            "kcal": round(minutes * (9.5 if kind == "RUNNING" else 6.2), 0),
            "heart_rate_avg": round(_spread(persona, f"hra-{back}", 118, 152), 0),
            "active_zone_min": round(minutes * 0.7, 0),
        }
        if distance:
            exercise["distance_km"] = round(distance * stretch, 2)
        found.append(exercise)
    return found


def _event(
    persona: Persona,
    kind: str,
    payload: dict[str, Any],
    ts: datetime,
    received: datetime,
    key: str,
) -> dict[str, Any]:
    dedup = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "ts": ts,
        "received": received,
        "source": SOURCE,
        "type": kind,
        "payload": json.dumps(payload),
        "dedup": f"demo:{kind}:{key}:{dedup}",
        "user": persona.id,
    }


def events(persona: Persona, today: date) -> list[dict[str, Any]]:
    alex = persona.key == "alex"
    found = []
    noon = time(12, 0, tzinfo=UTC)
    profile = {
        "blood_type": "A+" if alex else "0+",
        "sex": "male" if alex else "female",
        "birth_date": "1999-06-14" if alex else "1996-02-03",
        "height_cm": 178.0 if alex else 166.0,
        "walking_stride_cm": 74.0 if alex else 68.0,
        "running_stride_cm": 110.0 if alex else 98.0,
        "irn_enrolled": alex,
    }
    now = datetime.combine(today, time(8, 5, tzinfo=UTC))
    found.append(_event(persona, "health.profile", profile, now, now, "profile"))
    name, kind = BANDS[persona.key]
    device = {
        "id": f"band-{persona.key}",
        "name": name,
        "kind": kind,
        "battery_pct": 64 if alex else 18,
        "battery": "medium" if alex else "low",
        "last_sync": now.isoformat(),
    }
    found.append(_event(persona, "health.device", device, now, now, "band"))
    scale = {"id": f"scale-{persona.key}", "name": SCALES[persona.key], "kind": "scale"}
    found.append(_event(persona, "health.device", scale, now, now, "scale"))

    for back in range(DAYS, -1, -1):
        day = today - timedelta(days=back)
        ts = datetime.combine(day, noon)
        late = datetime.combine(day, time(21, 30, tzinfo=UTC))
        if back == 0:
            late = datetime.combine(day, time(8, 10, tzinfo=UTC))
        count = _steps(persona, day, back)
        if count is None:
            continue
        if back == 0:
            count = round(count * 0.42)
        steps = {"date": day.isoformat(), "steps": count}
        found.append(_event(persona, "health.steps", steps, ts, late, f"steps-{day}"))
        full = max(count, 3000)
        daily = {"date": day.isoformat(), "metrics": _metrics(persona, day, back, full)}
        found.append(_event(persona, "health.daily", daily, ts, late, f"daily-{day}"))
        woke = datetime.combine(day, time(8, 10, tzinfo=UTC))
        night = _night(persona, day, back)
        if night is not None:
            found.append(_event(persona, "health.sleep", night, woke, woke, f"sleep-{day}"))
        if back > 0:
            for exercise in _exercises(persona, day, back):
                found.append(
                    _event(persona, "health.exercise", exercise, late, late, exercise["id"])
                )
        if back < HEART_DAYS:
            upto = 1440 if back else 480
            found.append(
                _event(persona, "health.heart", _heart(persona, day, back, upto), ts, late, "hr")
            )
    return found


async def feed(connection: AsyncConnection, persona: Persona, today: date) -> int:
    batch = events(persona, today)
    for start in range(0, len(batch), 500):
        await connection.execute(INSERT, batch[start : start + 500])
    return len(batch)
