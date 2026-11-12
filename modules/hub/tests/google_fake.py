from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import parse_qs

import httpx

CLIENT_ID = "123-sintetico.apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX-sintetico-0000"
REFRESH = "1//refresh-sintetico"
DAY = date(2026, 10, 20)

DAILY = (
    "daily-resting-heart-rate",
    "daily-heart-rate-variability",
    "daily-oxygen-saturation",
    "daily-respiratory-rate",
    "daily-sleep-temperature-derivations",
    "daily-vo2-max",
)
FILTERS = {
    **{kind: ("date",) for kind in DAILY},
    "exercise": ("interval.civil_start_time",),
    "sleep": ("interval.end_time", "interval.civil_end_time"),
    "height": ("sample_time.physical_time", "sample_time.civil_time"),
    "respiratory-rate-sleep-summary": ("sample_time.physical_time", "sample_time.civil_time"),
    "electrocardiogram": ("interval.start_time",),
}
CONDITION = re.compile(r'^([a-z0-9_]+)\.([a-z_.]+) (>=|<) "([0-9T:Z+-]+)"$')


def refused(reason: str) -> httpx.Response:
    return httpx.Response(
        400,
        json={
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": f"Invalid data point filter: {reason}.",
                "details": [{"metadata": {"detailedReasons": reason}}],
            }
        },
    )


def check(kind: str, raw: str | None) -> httpx.Response | None:
    if not raw:
        return None
    for condition in raw.split(" AND "):
        found = CONDITION.match(condition)
        if not found:
            return refused("INVALID_DATA_POINT_FILTER_EXPRESSION_STRUCTURE")
        name, field, _, _ = found.groups()
        if name != kind.replace("-", "_"):
            return refused("INVALID_DATA_POINT_FILTER_DATA_TYPE_RESTRICTION")
        if field not in FILTERS.get(kind, ()):
            return refused("INVALID_DATA_POINT_FILTER_FIELD")
    return None


def civil(day: date) -> dict:
    return {"date": {"year": day.year, "month": day.month, "day": day.day}}


class FakeGoogle:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.refused_grant = False
        self.not_linked = False
        self.refused_kinds: set[str] = set()
        self.scope = " ".join(
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
        self.without: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.calls.append(f"{request.method} {url.path}")
        if url.host == "oauth2.googleapis.com":
            form = parse_qs(request.content.decode())
            if self.refused_grant:
                return httpx.Response(400, json={"error": "invalid_grant"})
            if form["client_secret"] != [CLIENT_SECRET]:
                return httpx.Response(401, json={"error": "invalid_client"})
            if form["grant_type"] == ["authorization_code"]:
                return httpx.Response(
                    200,
                    json={"access_token": "ya29.a", "refresh_token": REFRESH, "scope": self.scope},
                )
            assert form["refresh_token"] == [REFRESH]
            return httpx.Response(200, json={"access_token": "ya29.b", "expires_in": 3599})
        assert request.headers["authorization"] == "Bearer ya29.b"
        if self.not_linked:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "status": "FAILED_PRECONDITION",
                        "message": "The account is not linked to Google Health.",
                        "details": [{"reason": "ACCOUNT_NOT_LINKED"}],
                    }
                },
            )
        user_level = {"/v4/users/me/pairedDevices": "settings", "/v4/users/me/profile": "profile"}
        user_level["/v4/users/me/irnProfile"] = "irn"
        parts = url.path.split("/")
        needs = user_level.get(url.path) or {
            "electrocardiogram": "ecg",
            "irregular-rhythm-notification": "irn",
        }.get(parts[5] if len(parts) > 5 else "")
        if needs in self.without:
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": 403,
                        "status": "PERMISSION_DENIED",
                        "message": "Request had insufficient authentication scopes.",
                        "details": []
                        if needs == "settings"
                        else [{"reason": "MISSING_OAUTH_SCOPE"}],
                    }
                },
            )
        if url.path == "/v4/users/me/pairedDevices":
            return httpx.Response(200, json={"pairedDevices": [self.device()]})
        if url.path == "/v4/users/me/profile":
            return httpx.Response(
                200,
                json={
                    "name": "users/me/profile",
                    "age": 30,
                    "autoWalkingStrideLengthMm": 742,
                    "autoRunningStrideLengthMm": 1105,
                    "userConfiguredRunningStrideLengthMm": 1150,
                },
            )
        if url.path == "/v4/users/me/irnProfile":
            return httpx.Response(
                200, json={"name": "users/me/irnProfile", "enrollmentStatus": True}
            )
        path = url.path.removeprefix("/v4/users/me/dataTypes/")
        kind, _, method = path.partition("/dataPoints")
        if method == ":dailyRollUp":
            body = json.loads(request.content)
            return httpx.Response(200, json={"rollupDataPoints": self.daily(kind, body)})
        if method == ":rollUp" and kind == "steps":
            body = json.loads(request.content)
            return httpx.Response(200, json={"rollupDataPoints": self.minute_steps(body)})
        if method == ":rollUp":
            body = json.loads(request.content)
            return httpx.Response(200, json={"rollupDataPoints": self.heart(body)})
        if (wrong := check(kind, url.params.get("filter"))) is not None:
            return wrong
        if method == ":reconcile":
            return httpx.Response(200, json={"dataPoints": [self.sleep()]})
        if kind in self.refused_kinds:
            return httpx.Response(
                403, json={"error": {"code": 403, "message": "Not available for this account."}}
            )
        return httpx.Response(200, json={"dataPoints": self.listed(kind)})

    def daily(self, kind: str, body: dict) -> list[dict]:
        start, end = (date(**body["range"][edge]["date"]) for edge in ("start", "end"))
        if not start <= DAY < end:
            return []
        value = {
            "steps": {"steps": {"countSum": "9120"}},
            "distance": {"distance": {"millimetersSum": "6540000"}},
            "floors": {"floors": {"countSum": "7"}},
            "active-energy-burned": {"activeEnergyBurned": {"kcalSum": 410.5}},
            "total-calories": {"totalCalories": {"kcalSum": 2210.5}},
            "active-zone-minutes": {
                "activeZoneMinutes": {
                    "sumInFatBurnHeartZone": "20",
                    "sumInCardioHeartZone": "8",
                    "sumInPeakHeartZone": "2",
                }
            },
            "active-minutes": {
                "activeMinutes": {
                    "activeMinutesRollupByActivityLevel": [
                        {"activityLevel": "LIGHT", "activeMinutesSum": "184"},
                        {"activityLevel": "MODERATE", "activeMinutesSum": "26"},
                        {"activityLevel": "VIGOROUS", "activeMinutesSum": "11"},
                    ]
                }
            },
            "sedentary-period": {"sedentaryPeriod": {"durationSum": "34200s"}},
            "time-in-heart-rate-zone": {
                "timeInHeartRateZone": {
                    "timeInHeartRateZones": [
                        {"heartRateZone": "LIGHT", "duration": "5400s"},
                        {"heartRateZone": "MODERATE", "duration": "1200s"},
                        {"heartRateZone": "VIGOROUS", "duration": "480s"},
                        {"heartRateZone": "PEAK", "duration": "60s"},
                    ]
                }
            },
            "heart-rate": {
                "heartRate": {
                    "beatsPerMinuteMin": 52,
                    "beatsPerMinuteAvg": 71.4,
                    "beatsPerMinuteMax": 148,
                }
            },
        }[kind]
        return [{"civilStartTime": civil(DAY), "civilEndTime": civil(DAY), **value}]

    def heart(self, body: dict) -> list[dict]:
        if body["windowSize"] == "5s":
            return self.exercise_heart(body)
        if not body["range"]["startTime"].startswith("2026-10-19T22:00"):
            return []
        return [
            {
                "startTime": "2026-10-20T06:00:00Z",
                "endTime": "2026-10-20T06:05:00Z",
                "heartRate": {
                    "beatsPerMinuteMin": 55,
                    "beatsPerMinuteAvg": 58,
                    "beatsPerMinuteMax": 63,
                },
            },
            {
                "startTime": "2026-10-20T06:05:00Z",
                "endTime": "2026-10-20T06:10:00Z",
                "heartRate": {
                    "beatsPerMinuteMin": 60,
                    "beatsPerMinuteAvg": 75,
                    "beatsPerMinuteMax": 92,
                },
            },
        ]

    def minute_steps(self, body: dict) -> list[dict]:
        if not body["range"]["startTime"].startswith("2026-10-19T22:00"):
            return []
        return [
            {
                "startTime": "2026-10-20T06:05:00Z",
                "endTime": "2026-10-20T06:06:00Z",
                "steps": {"countSum": "42"},
            }
        ]

    def exercise_heart(self, body: dict) -> list[dict]:
        if not body["range"]["startTime"].startswith("2026-10-20T16:00"):
            return []
        return [
            {
                "startTime": f"2026-10-20T16:00:{second:02d}Z",
                "endTime": f"2026-10-20T16:00:{second + 5:02d}Z",
                "heartRate": {"beatsPerMinuteAvg": bpm} if bpm else {},
            }
            for second, bpm in ((0, 92), (5, 95.4), (10, None), (15, 101))
        ]

    def sleep(self) -> dict:
        return {
            "dataPointName": "users/me/dataTypes/sleep/dataPoints/noche-sintetica",
            "sleep": {
                "type": "STAGES",
                "interval": {
                    "startTime": "2026-10-19T22:30:00Z",
                    "startUtcOffset": "7200s",
                    "endTime": "2026-10-20T05:45:00Z",
                    "endUtcOffset": "7200s",
                },
                "stages": [
                    {
                        "startTime": "2026-10-19T22:30:00Z",
                        "endTime": "2026-10-19T22:45:00Z",
                        "startUtcOffset": "7200s",
                        "endUtcOffset": "7200s",
                        "type": "LIGHT",
                    },
                    {
                        "startTime": "2026-10-19T22:45:00Z",
                        "endTime": "2026-10-20T05:45:00Z",
                        "startUtcOffset": "7200s",
                        "endUtcOffset": "7200s",
                        "type": "DEEP",
                    },
                ],
                "metadata": {"mainSleep": True, "processed": True},
                "outOfBedSegments": [
                    {"startTime": "2026-10-20T02:10:00Z", "endTime": "2026-10-20T02:14:00Z"}
                ],
                "summary": {
                    "minutesAsleep": "400",
                    "minutesAwake": "35",
                    "minutesInSleepPeriod": "435",
                    "minutesToFallAsleep": "9",
                    "minutesAfterWakeUp": "6",
                    "stagesSummary": [
                        {"type": "DEEP", "minutes": "80", "count": "4"},
                        {"type": "REM", "minutes": "95", "count": "5"},
                        {"type": "LIGHT", "minutes": "225", "count": "20"},
                        {"type": "AWAKE", "minutes": "35", "count": "12"},
                    ],
                },
            },
        }

    def listed(self, kind: str) -> list[dict]:
        daily = {
            "daily-resting-heart-rate": {
                "dailyRestingHeartRate": {"date": civil(DAY)["date"], "beatsPerMinute": "57"}
            },
            "daily-heart-rate-variability": {
                "dailyHeartRateVariability": {
                    "date": civil(DAY)["date"],
                    "averageHeartRateVariabilityMilliseconds": 41.3,
                    "nonRemHeartRateBeatsPerMinute": 53.2,
                    "deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds": 48.7,
                }
            },
            "daily-oxygen-saturation": {
                "dailyOxygenSaturation": {
                    "date": civil(DAY)["date"],
                    "averagePercentage": 96.4,
                    "lowerBoundPercentage": 93,
                    "upperBoundPercentage": 99,
                }
            },
            "daily-respiratory-rate": {
                "dailyRespiratoryRate": {"date": civil(DAY)["date"], "breathsPerMinute": 14.2}
            },
            "daily-sleep-temperature-derivations": {
                "dailySleepTemperatureDerivations": {
                    "date": civil(DAY)["date"],
                    "nightlyTemperatureCelsius": 33.9,
                    "baselineTemperatureCelsius": 34.2,
                }
            },
            "daily-vo2-max": {"dailyVo2Max": {"date": civil(DAY)["date"], "vo2Max": 47.5}},
            "exercise": {
                "name": "users/me/dataTypes/exercise/dataPoints/paseo-sintetico",
                "exercise": {
                    "exerciseType": "WALKING",
                    "displayName": "Caminar",
                    "interval": {
                        "startTime": "2026-10-20T16:00:00Z",
                        "startUtcOffset": "7200s",
                        "endTime": "2026-10-20T16:42:00Z",
                        "endUtcOffset": "7200s",
                    },
                    "activeDuration": "2400s",
                    "metricsSummary": {
                        "caloriesKcal": 180.4,
                        "distanceMillimeters": 3200000,
                        "steps": "4100",
                        "averageHeartRateBeatsPerMinute": "104",
                        "activeZoneMinutes": "12",
                        "elevationGainMillimeters": 38500,
                        "averageSpeedMillimetersPerSecond": 1333.3,
                        "heartRateZoneDurations": {
                            "lightTime": "1500s",
                            "moderateTime": "720s",
                            "vigorousTime": "180s",
                        },
                        "mobilityMetrics": {
                            "avgCadenceStepsPerMinute": 112.4,
                            "avgStrideLengthMillimeters": 741,
                        },
                    },
                    "exerciseMetadata": {"hasGps": True},
                },
            },
            "respiratory-rate-sleep-summary": {
                "respiratoryRateSleepSummary": {
                    "sampleTime": {
                        "physicalTime": "2026-10-20T05:45:00Z",
                        "civilTime": {**civil(DAY), "time": {"hours": 7, "minutes": 45}},
                    },
                    "fullSleepStats": {"breathsPerMinute": 14.2},
                    "deepSleepStats": {"breathsPerMinute": 13.1},
                    "lightSleepStats": {"breathsPerMinute": 14.4},
                    "remSleepStats": {"breathsPerMinute": 15.0},
                }
            },
            "electrocardiogram": {
                "name": "users/me/dataTypes/electrocardiogram/dataPoints/ecg-sintetico",
                "electrocardiogram": {
                    "interval": {
                        "startTime": "2026-10-20T09:00:00Z",
                        "startUtcOffset": "7200s",
                        "endTime": "2026-10-20T09:00:30Z",
                        "endUtcOffset": "7200s",
                    },
                    "resultClassification": "NORMAL_SINUS_RHYTHM",
                    "waveformSamples": [0, 12, 80, -20, 3],
                    "beatsPerMinuteAvg": "64",
                    "samplingFrequencyHertz": 250,
                    "millivoltsScalingFactor": 1000,
                    "leadNumber": 1,
                    "medicalDeviceInfo": {"deviceModel": "Pulsera sintética"},
                },
            },
            "irregular-rhythm-notification": {
                "name": "users/me/dataTypes/irregular-rhythm-notification/dataPoints/irn-sintetico",
                "irregularRhythmNotification": {
                    "interval": {
                        "startTime": "2026-10-20T01:00:00Z",
                        "startUtcOffset": "7200s",
                        "endTime": "2026-10-20T03:00:00Z",
                        "endUtcOffset": "7200s",
                    },
                    "alertWindows": [
                        {"startTime": "2026-10-20T01:00:00Z", "positive": True},
                        {"startTime": "2026-10-20T01:30:00Z", "positive": True},
                        {"startTime": "2026-10-20T02:00:00Z", "positive": False},
                    ],
                },
            },
            "height": {
                "height": {
                    "sampleTime": {"physicalTime": "2026-10-01T08:00:00Z"},
                    "heightMillimeters": "1755",
                }
            },
        }
        return [daily[kind]]

    def device(self) -> dict:
        return {
            "name": "users/me/pairedDevices/pulsera-sintetica",
            "deviceType": "TRACKER",
            "deviceVersion": "Pulsera sintética",
            "batteryStatus": "High",
            "batteryLevel": 82,
            "lastSyncTime": "2026-10-20T17:40:00Z",
            "macAddress": "00:00:00:00:00:00",
            "features": ["STEPS", "HEART_RATE", "SPO2"],
        }
