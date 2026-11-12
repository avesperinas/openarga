from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from hub.declare import Provider, Secret, Sync
from hub.providers import Fetched, SourceError

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://health.googleapis.com/v4/users/me"
SCOPES = tuple(
    f"https://www.googleapis.com/auth/googlehealth.{name}.readonly"
    for name in (
        "activity_and_fitness",
        "health_metrics_and_measurements",
        "sleep",
        "profile",
        "location",
        "ecg",
        "irn",
        "settings",
    )
)
CLIENT_ID = "client_id"
CLIENT_SECRET = "client_secret"
REFRESH = "refresh_token"

MADRID = ZoneInfo("Europe/Madrid")
FIRST_DAYS = 30
OVERLAP_DAYS = 2
SHORT_RANGE = 14
HEART_STEP_MINUTES = 1
EXERCISE_HEART_SECONDS = 5

METRICS: dict[str, tuple[float, float]] = {
    "heart_rate_min": (20, 250),
    "heart_rate_avg": (20, 250),
    "heart_rate_max": (20, 250),
    "resting_heart_rate": (20, 200),
    "sleep_heart_rate": (20, 200),
    "hrv_ms": (0, 500),
    "hrv_deep_ms": (0, 500),
    "vo2max": (5, 100),
    "active_kcal": (0, 20_000),
    "basal_kcal": (0, 10_000),
    "distance_km": (0, 500),
    "flights": (0, 1_000),
    "active_zone_min": (0, 1_440),
    "light_active_min": (0, 1_440),
    "moderate_active_min": (0, 1_440),
    "vigorous_active_min": (0, 1_440),
    "sedentary_min": (0, 1_440),
    "hr_zone_light_min": (0, 1_440),
    "hr_zone_moderate_min": (0, 1_440),
    "hr_zone_vigorous_min": (0, 1_440),
    "hr_zone_peak_min": (0, 1_440),
    "respiratory_rate": (0, 100),
    "respiratory_rate_deep": (0, 100),
    "respiratory_rate_light": (0, 100),
    "respiratory_rate_rem": (0, 100),
    "spo2_pct": (50, 100),
    "spo2_min_pct": (50, 100),
    "spo2_max_pct": (50, 100),
    "skin_temp_delta_c": (-10, 10),
}

STAGES = {"AWAKE": "awake", "LIGHT": "light", "DEEP": "deep", "REM": "rem"}
SEGMENT = {**STAGES, "ASLEEP": "asleep", "RESTLESS": "restless"}


@dataclass(frozen=True)
class App:
    client_id: str
    client_secret: str


def normalise(key: str, raw: str) -> str:
    value = raw.strip()
    if key == CLIENT_ID and not value.endswith(".apps.googleusercontent.com"):
        raise ValueError(
            "eso no parece un Client ID de Google: acaba en .apps.googleusercontent.com"
        )
    if key == CLIENT_SECRET and (len(value) < 10 or " " in value):
        raise ValueError("eso no parece un Client secret de Google: empieza por GOCSPX-")
    return value


def authorization_url(app: App, state: str, redirect: str) -> str:
    return f"{AUTH}?" + urlencode(
        {
            "client_id": app.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )


def _oauth_error(response: httpx.Response, doing: str) -> SourceError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = str(body.get("error") or response.status_code)
    if error == "invalid_grant":
        return SourceError(
            "Google ya no acepta la autorización: reconecta Google Health.", code="consent_over"
        )
    if error in ("invalid_client", "unauthorized_client"):
        return SourceError(
            "Google no reconoce el cliente: comprueba el Client ID y el secret en Google Cloud."
        )
    detail = body.get("error_description") or ""
    return SourceError(
        f"Google contesta {error} al {doing}{': ' + detail if detail else ''}",
        transient=response.status_code >= 500,
    )


async def exchange(client: httpx.AsyncClient, app: App, code: str, redirect: str) -> str:
    response = await client.post(
        TOKEN,
        data={
            "code": code,
            "client_id": app.client_id,
            "client_secret": app.client_secret,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        raise _oauth_error(response, "autorizar")
    body = response.json()
    granted = set(str(body.get("scope") or "").split())
    missing = [scope.rsplit(".", 2)[-2] for scope in SCOPES if scope not in granted]
    if granted and missing:
        raise SourceError(
            f"Faltan permisos al autorizar ({', '.join(missing)}): vuelve a conectar y marca "
            "todas las casillas."
        )
    refresh = body.get("refresh_token")
    if not refresh:
        raise SourceError("Google no ha dado un refresh token: vuelve a conectar.")
    return str(refresh)


async def access(client: httpx.AsyncClient, app: App, refresh: str) -> str:
    try:
        response = await client.post(
            TOKEN,
            data={
                "client_id": app.client_id,
                "client_secret": app.client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
            timeout=30.0,
        )
    except httpx.HTTPError as error:
        raise SourceError(f"Google no contesta ({type(error).__name__})", transient=True) from error
    if response.status_code != 200:
        raise _oauth_error(response, "renovar el acceso")
    return str(response.json()["access_token"])


class Health:
    def __init__(self, client: httpx.AsyncClient, token: str):
        self.client = client
        self.headers = {"authorization": f"Bearer {token}"}

    async def call(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        try:
            response = await self.client.request(
                method, f"{API}/{path}", headers=self.headers, timeout=60.0, **kw
            )
        except httpx.HTTPError as error:
            raise SourceError(
                f"Google Health no contesta ({type(error).__name__})", transient=True
            ) from error
        if response.status_code == 200:
            return response.json()
        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        reasons = [one.get("reason") for one in error.get("details", []) if one.get("reason")]
        where = path.split("/")[1] if path.startswith("dataTypes/") else path
        scopes = "insufficient authentication scopes" in str(error.get("message", "")).lower()
        if "MISSING_OAUTH_SCOPE" in reasons or "MISSING_OAUTH_SCOPE" in str(error) or scopes:
            raise SourceError(
                f"Falta un permiso para {where}: reconecta Google Health y marca todas las "
                "casillas."
            )
        if "ACCOUNT_NOT_LINKED" in reasons:
            raise SourceError(
                "Tu cuenta no tiene perfil en Google Health: ábrela en la app Google Health."
            )
        if response.status_code == 401:
            raise SourceError(
                "Google Health no acepta el acceso: reconecta Google Health.", code="consent_over"
            )
        if response.status_code == 429:
            raise SourceError("Google Health pide esperar.", rate_limited=True)
        raise SourceError(
            f"Google Health contesta {response.status_code} en {where}: "
            f"{error.get('message', '')}".rstrip(": "),
            transient=response.status_code >= 500,
        )

    async def pages(self, method: str, path: str, key: str, **kw: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        token = None
        for _ in range(50):
            if token:
                if method == "GET":
                    kw["params"] = {**kw.get("params", {}), "pageToken": token}
                else:
                    kw["json"] = {**kw.get("json", {}), "pageToken": token}
            body = await self.call(method, path, **kw)
            found.extend(body.get(key) or [])
            token = body.get("nextPageToken")
            if not token:
                break
        return found

    async def daily(self, kind: str, start: date, end: date) -> list[dict[str, Any]]:
        return await self.pages(
            "POST",
            f"dataTypes/{kind}/dataPoints:dailyRollUp",
            "rollupDataPoints",
            json={"range": {"start": civil(start), "end": civil(end)}, "windowSizeDays": 1},
        )

    async def listed(self, kind: str, filter: str = "", page: int = 1000) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"pageSize": page}
        if filter:
            params["filter"] = filter
        return await self.pages("GET", f"dataTypes/{kind}/dataPoints", "dataPoints", params=params)

    async def sleeps(self, since: date) -> list[dict[str, Any]]:
        return await self.pages(
            "GET",
            "dataTypes/sleep/dataPoints:reconcile",
            "dataPoints",
            params={
                "filter": f'sleep.interval.civil_end_time >= "{since.isoformat()}"',
                "pageSize": 25,
            },
        )

    async def ecgs(self, since: date) -> list[dict[str, Any]]:
        start = datetime.combine(since, time(), MADRID)
        return await self.pages(
            "GET",
            "dataTypes/electrocardiogram/dataPoints",
            "dataPoints",
            params={"filter": f'electrocardiogram.interval.start_time >= "{instant(start)}"'},
        )

    async def devices(self) -> list[dict[str, Any]]:
        return await self.pages("GET", "pairedDevices", "pairedDevices", params={"pageSize": 100})

    async def profile(self) -> dict[str, Any]:
        return await self.call("GET", "profile")

    async def irn_profile(self) -> dict[str, Any]:
        return await self.call("GET", "irnProfile")

    async def heart(self, day: date) -> list[dict[str, Any]]:
        start = datetime.combine(day, time(), MADRID)
        end = datetime.combine(day + timedelta(days=1), time(), MADRID)
        return await self.pages(
            "POST",
            "dataTypes/heart-rate/dataPoints:rollUp",
            "rollupDataPoints",
            json={
                "range": {"startTime": instant(start), "endTime": instant(end)},
                "windowSize": f"{HEART_STEP_MINUTES * 60}s",
                "pageSize": 1440,
            },
        )

    async def steps_by_minute(self, day: date) -> list[dict[str, Any]]:
        start = datetime.combine(day, time(), MADRID)
        end = datetime.combine(day + timedelta(days=1), time(), MADRID)
        return await self.pages(
            "POST",
            "dataTypes/steps/dataPoints:rollUp",
            "rollupDataPoints",
            json={
                "range": {"startTime": instant(start), "endTime": instant(end)},
                "windowSize": f"{HEART_STEP_MINUTES * 60}s",
                "pageSize": 1440,
            },
        )

    async def exercise_heart(self, start: str, end: str) -> list[dict[str, Any]]:
        return await self.pages(
            "POST",
            "dataTypes/heart-rate/dataPoints:rollUp",
            "rollupDataPoints",
            json={
                "range": {"startTime": start, "endTime": end},
                "windowSize": f"{EXERCISE_HEART_SECONDS}s",
                "pageSize": 10000,
            },
        )


def field_of(kind: str) -> str:
    return kind.replace("-", "_")


def civil(day: date) -> dict[str, Any]:
    return {"date": {"year": day.year, "month": day.month, "day": day.day}}


def instant(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def day_of(raw: dict[str, Any] | None) -> date | None:
    if not raw:
        return None
    found = raw.get("date", raw)
    try:
        return date(int(found["year"]), int(found["month"]), int(found["day"]))
    except (KeyError, TypeError, ValueError):
        return None


def number(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def moment(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def offset(raw: str | None) -> timedelta:
    found = re.fullmatch(r"(-?\d+(?:\.\d+)?)s", raw or "")
    return timedelta(seconds=float(found.group(1))) if found else timedelta()


def local(raw: str, utc_offset: str | None) -> str:
    return moment(raw).astimezone(timezone(offset(utc_offset))).isoformat()


def digest(values: Any) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]


def kept(key: str, value: float | None) -> float | None:
    if value is None:
        return None
    low, high = METRICS[key]
    return round(value, 2) if low <= value <= high else None


def daily_metrics(rollups: dict[str, list[dict[str, Any]]]) -> dict[date, dict[str, float]]:
    days: dict[date, dict[str, float | None]] = {}

    def put(day: date | None, key: str, value: float | None) -> None:
        if day is not None and value is not None:
            days.setdefault(day, {})[key] = value

    for point in rollups.get("steps", []):
        put(
            day_of(point.get("civilStartTime")),
            "steps",
            number(point.get("steps", {}).get("countSum")),
        )
    for point in rollups.get("distance", []):
        mm = number(point.get("distance", {}).get("millimetersSum"))
        put(day_of(point.get("civilStartTime")), "distance_km", None if mm is None else mm / 1e6)
    for point in rollups.get("floors", []):
        put(
            day_of(point.get("civilStartTime")),
            "flights",
            number(point.get("floors", {}).get("countSum")),
        )
    for point in rollups.get("active-energy-burned", []):
        put(
            day_of(point.get("civilStartTime")),
            "active_kcal",
            number(point.get("activeEnergyBurned", {}).get("kcalSum")),
        )
    for point in rollups.get("total-calories", []):
        put(
            day_of(point.get("civilStartTime")),
            "total_kcal",
            number(point.get("totalCalories", {}).get("kcalSum")),
        )
    for point in rollups.get("active-zone-minutes", []):
        zones = point.get("activeZoneMinutes", {})
        parts = [number(zones.get(key)) for key in zones]
        values = [one for one in parts if one is not None]
        put(day_of(point.get("civilStartTime")), "active_zone_min", sum(values) if values else None)
    levels = {"LIGHT": "light_active_min", "MODERATE": "moderate_active_min"}
    levels["VIGOROUS"] = "vigorous_active_min"
    for point in rollups.get("active-minutes", []):
        day = day_of(point.get("civilStartTime"))
        by_level = (point.get("activeMinutes") or {}).get("activeMinutesRollupByActivityLevel")
        for one in by_level or []:
            if key := levels.get(one.get("activityLevel")):
                put(day, key, number(one.get("activeMinutesSum")))
    zones = {"LIGHT": "hr_zone_light_min", "MODERATE": "hr_zone_moderate_min"}
    zones |= {"VIGOROUS": "hr_zone_vigorous_min", "PEAK": "hr_zone_peak_min"}
    for point in rollups.get("time-in-heart-rate-zone", []):
        day = day_of(point.get("civilStartTime"))
        by_zone = (point.get("timeInHeartRateZone") or {}).get("timeInHeartRateZones")
        for one in by_zone or []:
            if (key := zones.get(one.get("heartRateZone"))) and one.get("duration"):
                put(day, key, offset(one["duration"]).total_seconds() / 60)
    for point in rollups.get("sedentary-period", []):
        found = (point.get("sedentaryPeriod") or {}).get("durationSum")
        put(
            day_of(point.get("civilStartTime")),
            "sedentary_min",
            offset(found).total_seconds() / 60 if found else None,
        )
    for point in rollups.get("heart-rate", []):
        heart = point.get("heartRate", {})
        day = day_of(point.get("civilStartTime"))
        put(day, "heart_rate_min", number(heart.get("beatsPerMinuteMin")))
        put(day, "heart_rate_avg", number(heart.get("beatsPerMinuteAvg")))
        put(day, "heart_rate_max", number(heart.get("beatsPerMinuteMax")))
    for values in days.values():
        total, active = values.pop("total_kcal", None), values.get("active_kcal")
        if total is not None and active is not None and total >= active:
            values["basal_kcal"] = total - active
    return {day: {k: v for k, v in values.items() if v is not None} for day, values in days.items()}


DAILY_KINDS = {
    "daily-resting-heart-rate": (
        "dailyRestingHeartRate",
        lambda one: {"resting_heart_rate": number(one.get("beatsPerMinute"))},
    ),
    "daily-heart-rate-variability": (
        "dailyHeartRateVariability",
        lambda one: {
            "hrv_ms": number(one.get("averageHeartRateVariabilityMilliseconds")),
            "sleep_heart_rate": number(one.get("nonRemHeartRateBeatsPerMinute")),
            "hrv_deep_ms": number(
                one.get("deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds")
            ),
        },
    ),
    "daily-oxygen-saturation": (
        "dailyOxygenSaturation",
        lambda one: {
            "spo2_pct": number(one.get("averagePercentage")),
            "spo2_min_pct": number(one.get("lowerBoundPercentage")),
            "spo2_max_pct": number(one.get("upperBoundPercentage")),
        },
    ),
    "daily-respiratory-rate": (
        "dailyRespiratoryRate",
        lambda one: {"respiratory_rate": number(one.get("breathsPerMinute"))},
    ),
    "daily-sleep-temperature-derivations": (
        "dailySleepTemperatureDerivations",
        lambda one: {
            "skin_temp_delta_c": (
                None
                if number(one.get("baselineTemperatureCelsius")) is None
                or number(one.get("nightlyTemperatureCelsius")) is None
                else number(one["nightlyTemperatureCelsius"])
                - number(one["baselineTemperatureCelsius"])
            )
        },
    ),
    "daily-vo2-max": ("dailyVo2Max", lambda one: {"vo2max": number(one.get("vo2Max"))}),
}


def breathing(points: list[dict[str, Any]]) -> dict[date, dict[str, float]]:
    days: dict[date, dict[str, float]] = {}
    for point in points:
        one = point.get("respiratoryRateSleepSummary") or {}
        civil_time = (one.get("sampleTime") or {}).get("civilTime")
        day = day_of(civil_time)
        for key, stats in (
            ("respiratory_rate_deep", one.get("deepSleepStats")),
            ("respiratory_rate_light", one.get("lightSleepStats")),
            ("respiratory_rate_rem", one.get("remSleepStats")),
        ):
            value = number((stats or {}).get("breathsPerMinute"))
            if day is not None and value is not None:
                days.setdefault(day, {})[key] = value
    return days


def per_day(kind: str, points: list[dict[str, Any]]) -> dict[date, dict[str, float]]:
    field, read = DAILY_KINDS[kind]
    days: dict[date, dict[str, float]] = {}
    for point in points:
        one = point.get(field) or {}
        day = day_of(one.get("date"))
        if day is None:
            continue
        for key, value in read(one).items():
            if value is not None:
                days.setdefault(day, {})[key] = value
    return days


def day_events(day: date, values: dict[str, float]) -> list[dict[str, Any]]:
    ts = f"{day.isoformat()}T12:00:00+00:00"
    events: list[dict[str, Any]] = []
    steps = values.get("steps")
    if steps is not None and 0 <= steps <= 300_000:
        count = round(steps)
        events.append(
            {
                "ts": ts,
                "type": "health.steps",
                "payload": {"date": day.isoformat(), "steps": count},
                "dedup_hash": f"google:steps:{day.isoformat()}:{count}",
            }
        )
    metrics = {key: found for key in METRICS if (found := kept(key, values.get(key))) is not None}
    if metrics:
        events.append(
            {
                "ts": ts,
                "type": "health.daily",
                "payload": {"date": day.isoformat(), "metrics": metrics},
                "dedup_hash": f"google:daily:{day.isoformat()}:{digest(metrics)}",
            }
        )
    return events


def minute_steps(day: date, points: list[dict[str, Any]]) -> dict[int, int]:
    found: dict[int, int] = {}
    for point in points or []:
        count = number((point.get("steps") or {}).get("countSum"))
        if count is None or not point.get("startTime"):
            continue
        at = moment(point["startTime"]).astimezone(MADRID)
        if at.date() == day:
            found[at.hour * 60 + at.minute] = max(0, min(1000, round(count)))
    return found


def heart_event(
    day: date, points: list[dict[str, Any]], steps: dict[int, int] | None = None
) -> dict[str, Any] | None:
    buckets = []
    for point in points:
        heart = point.get("heartRate") or {}
        low, avg, high = (
            number(heart.get(key))
            for key in ("beatsPerMinuteMin", "beatsPerMinuteAvg", "beatsPerMinuteMax")
        )
        if low is None or avg is None or high is None or not point.get("startTime"):
            continue
        at = moment(point["startTime"]).astimezone(MADRID)
        if at.date() != day:
            continue
        values = [round(min(max(one, 20), 250), 1) for one in (low, avg, high)]
        bucket = {
            "minute": at.hour * 60 + at.minute,
            "min": values[0],
            "avg": values[1],
            "max": values[2],
        }
        if steps is not None:
            bucket["steps"] = steps.get(bucket["minute"], 0)
        buckets.append(bucket)
    if not buckets:
        return None
    buckets.sort(key=lambda one: one["minute"])
    payload = {"date": day.isoformat(), "step": HEART_STEP_MINUTES, "buckets": buckets}
    return {
        "ts": f"{day.isoformat()}T12:00:00+00:00",
        "type": "health.heart",
        "payload": payload,
        "dedup_hash": f"google:heart:{day.isoformat()}:{digest(buckets)}",
    }


def minutes(raw: Any) -> int | None:
    found = number(raw)
    return None if found is None else max(0, min(1440, round(found)))


def sleep_event(point: dict[str, Any]) -> dict[str, Any] | None:
    sleep = point.get("sleep") or {}
    interval = sleep.get("interval") or {}
    if not interval.get("startTime") or not interval.get("endTime"):
        return None
    summary = sleep.get("summary") or {}
    metadata = sleep.get("metadata") or {}
    end_local = local(interval["endTime"], interval.get("endUtcOffset"))
    stages: dict[str, int] = {}
    for one in summary.get("stagesSummary") or []:
        name = STAGES.get(one.get("type"))
        found = minutes(one.get("minutes"))
        if name and found is not None:
            stages[name] = found
    segments = [
        {
            "start": local(one["startTime"], one.get("startUtcOffset")),
            "end": local(one["endTime"], one.get("endUtcOffset")),
            "stage": SEGMENT[one["type"]],
        }
        for one in sleep.get("stages") or []
        if one.get("type") in SEGMENT and one.get("startTime") and one.get("endTime")
    ]
    asleep = minutes(summary.get("minutesAsleep"))
    if asleep is None:
        asleep = sum(value for key, value in stages.items() if key != "awake")
    identity = (
        point.get("dataPointName")
        or point.get("name")
        or metadata.get("externalId")
        or f"sleep:{interval['startTime']}"
    )
    payload: dict[str, Any] = {
        "id": str(identity),
        "date": end_local[:10],
        "start": local(interval["startTime"], interval.get("startUtcOffset")),
        "end": end_local,
        "minutes_asleep": asleep,
        "main": bool(metadata.get("mainSleep", not metadata.get("nap", False))),
        "segments": segments,
    }
    for key, raw in (
        ("minutes_awake", summary.get("minutesAwake")),
        ("minutes_in_bed", summary.get("minutesInSleepPeriod")),
        ("minutes_to_fall_asleep", summary.get("minutesToFallAsleep")),
    ):
        if (found := minutes(raw)) is not None:
            payload[key] = found
    if stages:
        payload["stages"] = stages
    awake = next(
        (one for one in summary.get("stagesSummary") or [] if one.get("type") == "AWAKE"), None
    )
    if awake is not None and (count := number(awake.get("count"))) is not None:
        payload["awakenings"] = max(0, min(500, round(count)))
    if (found := minutes(summary.get("minutesAfterWakeUp"))) is not None:
        payload["minutes_after_wake_up"] = found
    out = [
        moment(one["endTime"]) - moment(one["startTime"])
        for one in sleep.get("outOfBedSegments") or []
        if one.get("startTime") and one.get("endTime")
    ]
    if out:
        payload["minutes_out_of_bed"] = minutes(sum(out, timedelta()).total_seconds() / 60)
    return {
        "ts": interval["endTime"],
        "type": "health.sleep",
        "payload": payload,
        "dedup_hash": f"google:sleep:{payload['id']}:{digest(payload)}",
    }


def exercise_beats(start: str, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    began = moment(start)
    beats = []
    for point in points:
        avg = number((point.get("heartRate") or {}).get("beatsPerMinuteAvg"))
        if avg is None or not point.get("startTime") or not 20 <= avg <= 250:
            continue
        seconds = round((moment(point["startTime"]) - began).total_seconds())
        if 0 <= seconds <= 86400:
            beats.append({"s": seconds, "bpm": round(avg, 1)})
    beats.sort(key=lambda one: one["s"])
    return beats


def exercise_event(
    point: dict[str, Any], heart: list[dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    exercise = point.get("exercise") or {}
    interval = exercise.get("interval") or {}
    if not interval.get("startTime") or not interval.get("endTime"):
        return None
    summary = exercise.get("metricsSummary") or {}
    start = local(interval["startTime"], interval.get("startUtcOffset"))
    end = local(interval["endTime"], interval.get("endUtcOffset"))
    active = offset(exercise.get("activeDuration")) if exercise.get("activeDuration") else None
    whole = moment(interval["endTime"]) - moment(interval["startTime"])
    payload: dict[str, Any] = {
        "id": str(
            point.get("name") or point.get("dataPointName") or f"exercise:{interval['startTime']}"
        ),
        "kind": str(exercise.get("exerciseType") or "OTHER"),
        "name": str(exercise.get("displayName") or exercise.get("exerciseType") or "Entreno")[:60],
        "start": start,
        "end": end,
        "minutes": round((active or whole).total_seconds() / 60, 1),
    }
    distance = number(summary.get("distanceMillimeters"))
    climbed = number(summary.get("elevationGainMillimeters"))
    speed = number(summary.get("averageSpeedMillimetersPerSecond"))
    for key, value in (
        ("kcal", number(summary.get("caloriesKcal"))),
        ("distance_km", None if distance is None else round(distance / 1e6, 2)),
        ("steps", number(summary.get("steps"))),
        ("heart_rate_avg", number(summary.get("averageHeartRateBeatsPerMinute"))),
        ("active_zone_min", number(summary.get("activeZoneMinutes"))),
        ("elevation_gain_m", None if climbed is None else climbed / 1000),
        ("avg_speed_kmh", None if speed is None or speed <= 0 else speed * 3.6 / 1000),
    ):
        if value is not None:
            payload[key] = round(value) if key == "steps" else round(value, 1)
    zones = {
        name: round(offset(raw).total_seconds() / 60, 1)
        for name, raw in (
            ("light", (summary.get("heartRateZoneDurations") or {}).get("lightTime")),
            ("moderate", (summary.get("heartRateZoneDurations") or {}).get("moderateTime")),
            ("vigorous", (summary.get("heartRateZoneDurations") or {}).get("vigorousTime")),
            ("peak", (summary.get("heartRateZoneDurations") or {}).get("peakTime")),
        )
        if raw
    }
    if zones:
        payload["hr_zone_min"] = zones
    mobility = summary.get("mobilityMetrics") or {}
    stride = number(mobility.get("avgStrideLengthMillimeters"))
    for key, value, low, high in (
        ("cadence_spm", number(mobility.get("avgCadenceStepsPerMinute")), 0, 400),
        ("stride_length_cm", None if stride is None else stride / 10, 0, 400),
        ("run_vo2max", number(summary.get("runVo2Max")), 0, 100),
    ):
        if value is not None and low <= value <= high:
            payload[key] = round(value, 1)
    if (lengths := number(summary.get("totalSwimLengths"))) is not None and lengths >= 0:
        payload["swim_lengths"] = round(lengths)
    gps = (exercise.get("exerciseMetadata") or {}).get("hasGps")
    if gps is not None:
        payload["has_gps"] = bool(gps)
    if "heart_rate_avg" in payload and not 20 <= payload["heart_rate_avg"] <= 250:
        del payload["heart_rate_avg"]
    if payload["minutes"] > 1440:
        payload["minutes"] = 1440
    if heart and (beats := exercise_beats(interval["startTime"], heart)):
        payload["heart"] = beats
    return {
        "ts": interval["startTime"],
        "type": "health.exercise",
        "payload": payload,
        "dedup_hash": f"google:exercise:{payload['id']}:{digest(payload)}",
    }


def profile_event(
    points: list[dict[str, Any]],
    profile: dict[str, Any] | None,
    irn: dict[str, Any] | None,
    today: date,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    heights = [
        number((one.get("height") or {}).get("heightMillimeters"))
        for one in sorted(
            points,
            key=lambda one: (one.get("height") or {}).get("sampleTime", {}).get("physicalTime", ""),
        )
    ]
    found = [one for one in heights if one is not None and 500 <= one <= 2600]
    if found:
        payload["height_cm"] = round(found[-1] / 10, 1)
    for key, mine, auto, high in (
        (
            "walking_stride_cm",
            "userConfiguredWalkingStrideLengthMm",
            "autoWalkingStrideLengthMm",
            300,
        ),
        (
            "running_stride_cm",
            "userConfiguredRunningStrideLengthMm",
            "autoRunningStrideLengthMm",
            400,
        ),
    ):
        value = number((profile or {}).get(mine)) or number((profile or {}).get(auto))
        if value and 10 <= value / 10 <= high:
            payload[key] = round(value / 10, 1)
    if irn is not None and irn.get("enrollmentStatus") is not None:
        payload["irn_enrolled"] = bool(irn["enrollmentStatus"])
    if not payload:
        return None
    return {
        "ts": f"{today.isoformat()}T12:00:00+00:00",
        "type": "health.profile",
        "payload": payload,
        "dedup_hash": f"google:profile:{digest(payload)}",
    }


ECG_RESULTS = {
    "NORMAL_SINUS_RHYTHM": "normal_sinus_rhythm",
    "ATRIAL_FIBRILLATION": "atrial_fibrillation",
    "INCONCLUSIVE": "inconclusive",
    "INCONCLUSIVE_HIGH_HEART_RATE": "inconclusive_high_heart_rate",
    "INCONCLUSIVE_LOW_HEART_RATE": "inconclusive_low_heart_rate",
    "UNREADABLE": "unreadable",
    "NOT_ANALYZED": "not_analyzed",
}


def device_model(info: dict[str, Any] | None) -> str | None:
    found = str((info or {}).get("deviceModel") or "").strip()
    return found[:60] or None


def ecg_event(point: dict[str, Any]) -> dict[str, Any] | None:
    ecg = point.get("electrocardiogram") or {}
    interval = ecg.get("interval") or {}
    if not interval.get("startTime") or not interval.get("endTime"):
        return None
    payload: dict[str, Any] = {
        "id": str(point.get("name") or f"ecg:{interval['startTime']}"),
        "start": local(interval["startTime"], interval.get("startUtcOffset")),
        "end": local(interval["endTime"], interval.get("endUtcOffset")),
        "samples": [
            int(one) for one in ecg.get("waveformSamples") or [] if number(one) is not None
        ],
    }
    if result := ECG_RESULTS.get(ecg.get("resultClassification")):
        payload["result"] = result
    heart_rate = number(ecg.get("beatsPerMinuteAvg"))
    if heart_rate is not None and 20 <= heart_rate <= 250:
        payload["heart_rate_avg"] = heart_rate
    for key, raw, low, high in (
        ("sampling_hz", ecg.get("samplingFrequencyHertz"), 1, 10_000),
        ("millivolts_scale", ecg.get("millivoltsScalingFactor"), 1, 10**9),
        ("leads", ecg.get("leadNumber"), 1, 12),
    ):
        if (value := number(raw)) is not None and low <= value <= high:
            payload[key] = round(value)
    if model := device_model(ecg.get("medicalDeviceInfo")):
        payload["device"] = model
    return {
        "ts": interval["startTime"],
        "type": "health.ecg",
        "payload": payload,
        "dedup_hash": f"google:ecg:{payload['id']}:{digest(payload)}",
    }


def irn_event(point: dict[str, Any], since: date) -> dict[str, Any] | None:
    irn = point.get("irregularRhythmNotification") or {}
    interval = irn.get("interval") or {}
    if not interval.get("startTime") or not interval.get("endTime"):
        return None
    start = local(interval["startTime"], interval.get("startUtcOffset"))
    if date.fromisoformat(start[:10]) < since:
        return None
    windows = irn.get("alertWindows") or []
    payload: dict[str, Any] = {
        "id": str(point.get("name") or f"irn:{interval['startTime']}"),
        "start": start,
        "end": local(interval["endTime"], interval.get("endUtcOffset")),
        "windows": len(windows),
        "positive_windows": sum(1 for one in windows if one.get("positive")),
    }
    if model := device_model(irn.get("medicalDeviceInfo")):
        payload["device"] = model
    return {
        "ts": interval["startTime"],
        "type": "health.irn",
        "payload": payload,
        "dedup_hash": f"google:irn:{payload['id']}:{digest(payload)}",
    }


BATTERY = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low", "EMPTY": "empty"}


def device_event(device: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    if not device.get("name"):
        return None
    payload: dict[str, Any] = {
        "id": str(device["name"]),
        "name": str(device.get("deviceVersion") or "Pulsera")[:60],
        "kind": {"TRACKER": "tracker", "SCALE": "scale"}.get(device.get("deviceType"), "other"),
        "features": [str(one) for one in device.get("features") or []][:50],
    }
    level = number(device.get("batteryLevel"))
    if level is not None and 0 <= level <= 100:
        payload["battery_pct"] = round(level)
    if battery := BATTERY.get(str(device.get("batteryStatus") or "").upper()):
        payload["battery"] = battery
    if device.get("lastSyncTime"):
        payload["last_sync"] = moment(device["lastSyncTime"]).isoformat()
    return {
        "ts": now.isoformat(),
        "type": "health.device",
        "payload": payload,
        "dedup_hash": f"google:device:{payload['id']}:{digest(payload)}",
    }


def current() -> datetime:
    return datetime.now(UTC)


def window(last_ok: datetime | None, today: date) -> date:
    if last_ok is None:
        return today - timedelta(days=FIRST_DAYS - 1)
    since = last_ok.astimezone(MADRID).date() - timedelta(days=OVERLAP_DAYS)
    return max(since, today - timedelta(days=FIRST_DAYS - 1))


def hourly(moment: datetime) -> bool:
    return moment.astimezone(MADRID).minute < 15


def chunks(start: date, end: date, size: int) -> list[tuple[date, date]]:
    found = []
    cursor = start
    while cursor < end:
        stop = min(end, cursor + timedelta(days=size))
        found.append((cursor, stop))
        cursor = stop
    return found


SUMMED = (
    "steps",
    "distance",
    "floors",
    "active-energy-burned",
    "total-calories",
    "active-zone-minutes",
    "active-minutes",
    "time-in-heart-rate-zone",
    "sedentary-period",
    "heart-rate",
)


async def sync(
    client: httpx.AsyncClient,
    secrets: dict[str, str],
    connection: Any,
    *,
    now: datetime | None = None,
) -> Fetched:
    refresh = secrets.get(REFRESH)
    if not refresh:
        raise SourceError("Falta autorizar en Google: pulsa Reconectar.", code="consent_over")
    app = App(secrets[CLIENT_ID], secrets[CLIENT_SECRET])
    health = Health(client, await access(client, app, refresh))
    today = (now or current()).astimezone(MADRID).date()
    since = window(connection.last_ok, today)
    end = today + timedelta(days=1)

    missing: list[SourceError] = []

    async def tried(what: Any) -> Any:
        try:
            return await what
        except SourceError as error:
            if error.code or error.transient or error.rate_limited:
                raise
            missing.append(error)
            return None

    rollups: dict[str, list[dict[str, Any]]] = {}
    for kind in SUMMED:
        for low, high in chunks(since, end, SHORT_RANGE):
            found = await tried(health.daily(kind, low, high))
            if found is None:
                break
            rollups.setdefault(kind, []).extend(found)
    days = daily_metrics(rollups)
    for kind in DAILY_KINDS:
        points = await tried(health.listed(kind, f'{field_of(kind)}.date >= "{since.isoformat()}"'))
        for day, values in per_day(kind, points or []).items():
            days.setdefault(day, {}).update(values)
    kind = "respiratory-rate-sleep-summary"
    points = await tried(
        health.listed(kind, f'{field_of(kind)}.sample_time.civil_time >= "{since.isoformat()}"')
    )
    for day, values in breathing(points or []).items():
        days.setdefault(day, {}).update(values)

    events: list[dict[str, Any]] = []
    for day in sorted(days):
        if since <= day <= today:
            events.extend(day_events(day, days[day]))
    cursor = since if hourly(now or current()) else end
    while cursor <= today:
        points = await tried(health.heart(cursor))
        if points is None:
            break
        walked = await tried(health.steps_by_minute(cursor))
        moved = None if walked is None else minute_steps(cursor, walked)
        if (found := heart_event(cursor, points, moved)) is not None:
            events.append(found)
        cursor += timedelta(days=1)
    for point in await tried(health.sleeps(since)) or []:
        if (found := sleep_event(point)) is not None:
            events.append(found)
    exercises = await tried(
        health.listed(
            "exercise", f'exercise.interval.civil_start_time >= "{since.isoformat()}T00:00:00"', 25
        )
    )
    for point in exercises or []:
        interval = (point.get("exercise") or {}).get("interval") or {}
        heart = None
        if interval.get("startTime") and interval.get("endTime"):
            heart = await tried(health.exercise_heart(interval["startTime"], interval["endTime"]))
        if (found := exercise_event(point, heart)) is not None:
            events.append(found)
    for point in await tried(health.ecgs(since)) or []:
        if (found := ecg_event(point)) is not None:
            events.append(found)
    for point in await tried(health.listed("irregular-rhythm-notification", page=25)) or []:
        if (found := irn_event(point, since)) is not None:
            events.append(found)
    for device in await tried(health.devices()) or []:
        if (found := device_event(device, now or current())) is not None:
            events.append(found)
    profile = profile_event(
        await tried(health.listed("height", page=25)) or [],
        await tried(health.profile()),
        await tried(health.irn_profile()),
        today,
    )
    if profile is not None:
        events.append(profile)
    if missing and not events:
        raise missing[0]
    note = None
    if missing:
        note = "Google no dio todo: " + "; ".join(dict.fromkeys(str(one) for one in missing))
    return Fetched(events, note=note)


SOURCES = (
    Provider(
        id="google_health",
        name="Google Health",
        category="health",
        description="Lo que mide tu pulsera Fitbit: pasos, vitals, sueño con fases, VFC, SpO₂, "
        "temperatura, entrenos, electrocardiogramas, avisos de ritmo irregular y la batería, cada "
        "cuarto de hora. Va con tu propio cliente OAuth de Google Cloud: "
        "pega su id y su secreto, y al conectar te lleva a Google a autorizar.",
        capabilities=("sync",),
        secrets=(
            Secret(
                CLIENT_ID,
                "Client ID",
                "El de tu cliente OAuth de Google Cloud (Credentials): acaba en "
                ".apps.googleusercontent.com.",
            ),
            Secret(
                CLIENT_SECRET,
                "Client secret",
                "El secreto del mismo cliente: empieza por GOCSPX-.",
            ),
        ),
        emits=(
            "health.steps",
            "health.daily",
            "health.profile",
            "health.sleep",
            "health.heart",
            "health.exercise",
            "health.ecg",
            "health.irn",
            "health.device",
        ),
        available=True,
        schedule="2,17,32,47 * * * *",
        single=True,
        oauth=True,
        internal=(REFRESH,),
        sync=Sync("health", sync, policy="authorized"),
        normalise=normalise,
    ),
)
