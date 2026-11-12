#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import IO
from xml.etree.ElementTree import iterparse

URL = (
    os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/") + "/api/hub/push/apple-health"
)
STEPS = "HKQuantityTypeIdentifierStepCount"
BATCH = 250

Q = "HKQuantityTypeIdentifier"
C = "HKCategoryTypeIdentifier"
SUMS = {
    f"{Q}StepCount": "steps",
    f"{Q}DistanceWalkingRunning": "distance_km",
    f"{Q}DistanceCycling": "cycling_km",
    f"{Q}FlightsClimbed": "flights",
    f"{Q}ActiveEnergyBurned": "active_kcal",
    f"{Q}BasalEnergyBurned": "basal_kcal",
    f"{Q}AppleExerciseTime": "exercise_min",
    f"{Q}AppleStandTime": "stand_min",
}
MEANS = {
    f"{Q}RestingHeartRate": ("resting_heart_rate", 1),
    f"{Q}WalkingHeartRateAverage": ("walking_heart_rate", 1),
    f"{Q}HeartRateVariabilitySDNN": ("hrv_ms", 1),
    f"{Q}VO2Max": ("vo2max", 1),
    f"{Q}RespiratoryRate": ("respiratory_rate", 1),
    f"{Q}PhysicalEffort": ("physical_effort", 1),
    f"{Q}WalkingSpeed": ("walking_speed_kmh", 1),
    f"{Q}WalkingStepLength": ("step_length_cm", 1),
    f"{Q}WalkingDoubleSupportPercentage": ("double_support_pct", 100),
    f"{Q}WalkingAsymmetryPercentage": ("asymmetry_pct", 100),
    f"{Q}AppleWalkingSteadiness": ("steadiness_pct", 100),
    f"{Q}SixMinuteWalkTestDistance": ("six_minute_walk_m", 1),
    f"{Q}StairAscentSpeed": ("stair_up_ms", 1),
    f"{Q}StairDescentSpeed": ("stair_down_ms", 1),
    f"{Q}HeadphoneAudioExposure": ("headphone_db", 1),
    f"{Q}EnvironmentalAudioExposure": ("environment_db", 1),
}
COUNTS = {
    f"{C}HighHeartRateEvent": "high_heart_rate_events",
    f"{C}LowHeartRateEvent": "low_heart_rate_events",
    f"{C}AudioExposureEvent": "environment_noise_events",
    f"{C}HeadphoneAudioExposureEvent": "headphone_noise_events",
}
HEART_RATE = f"{Q}HeartRate"
STAND_HOUR = f"{C}AppleStandHour"
SLEEP = f"{C}SleepAnalysis"
MINDFUL = f"{C}MindfulSession"
HEIGHT = f"{Q}Height"
MOMENT = "%Y-%m-%d %H:%M:%S %z"

BLOOD = {
    "HKBloodTypeAPositive": "A+",
    "HKBloodTypeANegative": "A-",
    "HKBloodTypeBPositive": "B+",
    "HKBloodTypeBNegative": "B-",
    "HKBloodTypeABPositive": "AB+",
    "HKBloodTypeABNegative": "AB-",
    "HKBloodTypeOPositive": "0+",
    "HKBloodTypeONegative": "0-",
}
SEX = {
    "HKBiologicalSexFemale": "female",
    "HKBiologicalSexMale": "male",
    "HKBiologicalSexOther": "other",
}


def spread(element, value: float) -> list[tuple[str, float]]:
    start_text = element.get("startDate") or ""
    try:
        start = datetime.strptime(start_text, MOMENT)
        end = datetime.strptime(element.get("endDate") or "", MOMENT)
    except ValueError:
        return [(start_text[:10], value)]
    if end.date() <= start.date() or end <= start:
        return [(start_text[:10], value)]
    whole = (end - start).total_seconds()
    shares = []
    moment = start
    while moment < end:
        midnight = datetime.combine(moment.date() + timedelta(days=1), time(), moment.tzinfo)
        until = min(midnight, end)
        shares.append((moment.date().isoformat(), value * (until - moment).total_seconds() / whole))
        moment = until
    return shares


def records(source: IO[bytes]) -> Iterator[tuple[str, str, float]]:
    for _event, element in iterparse(source, events=("end",)):
        if element.tag == "Record" and element.get("type") == STEPS:
            value = element.get("value") or ""
            if value.replace(".", "", 1).isdigit():
                for day, share in spread(element, float(value)):
                    yield day, element.get("sourceName") or "?", share
        if element.tag in ("Record", "Workout", "ActivitySummary"):
            element.clear()


def per_day(samples: Iterator[tuple[str, str, float]]) -> dict[str, int]:
    by_source: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for day, source, value in samples:
        by_source[day][source] += value
    return {day: round(max(sources.values())) for day, sources in sorted(by_source.items())}


def minutes(element) -> float:
    start = datetime.strptime(element.get("startDate") or "", MOMENT)
    end = datetime.strptime(element.get("endDate") or "", MOMENT)
    return max((end - start).total_seconds() / 60, 0)


def union(spans: list[tuple[datetime, datetime]]) -> float:
    total = 0.0
    end_so_far: datetime | None = None
    for start, end in sorted(spans):
        if end_so_far is not None and start < end_so_far:
            start = end_so_far
        if end > start:
            total += (end - start).total_seconds() / 60
        end_so_far = end if end_so_far is None else max(end_so_far, end)
    return total


class Collected:
    def __init__(self) -> None:
        self.sums: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(float))
        )
        self.means: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self.counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.sleep: dict[tuple[str, str, str], list[tuple[datetime, datetime]]] = defaultdict(list)
        self.goals: dict[str, dict[str, float]] = defaultdict(dict)
        self.profile: dict[str, object] = {}

    def record(self, element) -> None:
        kind = element.get("type") or ""
        day = (element.get("startDate") or "")[:10]
        source = element.get("sourceName") or "?"
        raw = element.get("value") or ""
        if kind in SUMS or kind in MEANS or kind in (HEART_RATE, HEIGHT):
            try:
                value = float(raw)
            except ValueError:
                return
            if kind in SUMS:
                for share_day, share in spread(element, value):
                    self.sums[share_day][SUMS[kind]][source] += share
            elif kind in MEANS:
                key, factor = MEANS[kind]
                self.means[day][key].append(value * factor)
            elif kind == HEART_RATE:
                self.means[day]["heart_rate"].append(value)
            else:
                self.profile["height_cm"] = round(value, 1)
        elif kind in COUNTS:
            self.counts[day][COUNTS[kind]] += 1
        elif kind == STAND_HOUR and raw.endswith("Stood"):
            self.counts[day]["stand_hours"] += 1
        elif kind == MINDFUL:
            self.sums[day]["mindful_min"][source] += minutes(element)
        elif kind == SLEEP:
            what = "in_bed_min" if raw.endswith("InBed") else None
            what = what or ("sleep_min" if "Asleep" in raw else None)
            if what:
                start = datetime.strptime(element.get("startDate") or "", MOMENT)
                end = datetime.strptime(element.get("endDate") or "", MOMENT)
                woke = (element.get("endDate") or "")[:10]
                self.sleep[(woke, what, source)].append((start, end))

    def summary(self, element) -> None:
        day = element.get("dateComponents") or ""
        for attribute, key in (
            ("activeEnergyBurnedGoal", "move_goal_kcal"),
            ("appleExerciseTimeGoal", "exercise_goal_min"),
            ("appleStandHoursGoal", "stand_goal_hours"),
        ):
            try:
                value = float(element.get(attribute) or 0)
            except ValueError:
                continue
            if value > 0:
                self.goals[day][key] = value

    def me(self, element) -> None:
        blood = BLOOD.get(element.get("HKCharacteristicTypeIdentifierBloodType") or "")
        sex = SEX.get(element.get("HKCharacteristicTypeIdentifierBiologicalSex") or "")
        born = element.get("HKCharacteristicTypeIdentifierDateOfBirth") or ""
        medication = element.get("HKCharacteristicTypeIdentifierCardioFitnessMedicationsUse") or ""
        if blood:
            self.profile["blood_type"] = blood
        if sex:
            self.profile["sex"] = sex
        if len(born) >= 10:
            self.profile["birth_date"] = born[:10]
        if medication and "NotSet" not in medication:
            self.profile["cardio_medications"] = medication[:120]

    def days(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = defaultdict(dict)
        for day, keys in self.sums.items():
            for key, sources in keys.items():
                value = max(sources.values())
                out[day][key] = round(value) if key == "steps" else round(value, 2)
        for day, keys in self.means.items():
            for key, values in keys.items():
                if key == "heart_rate":
                    out[day]["heart_rate_min"] = round(min(values), 1)
                    out[day]["heart_rate_avg"] = round(statistics.fmean(values), 1)
                    out[day]["heart_rate_max"] = round(max(values), 1)
                else:
                    out[day][key] = round(statistics.fmean(values), 2)
        for day, keys in self.counts.items():
            out[day].update(keys)
        by_source: dict[tuple[str, str], list[float]] = defaultdict(list)
        for (day, key, _source), spans in self.sleep.items():
            by_source[(day, key)].append(union(spans))
        for (day, key), totals in by_source.items():
            out[day][key] = round(max(totals))
        for day, goals in self.goals.items():
            if day in out:
                out[day].update(goals)
        return {day: out[day] for day in sorted(out) if len(day) == 10}


def collect(source: IO[bytes]) -> Collected:
    found = Collected()
    for _event, element in iterparse(source, events=("end",)):
        if element.tag == "Record":
            found.record(element)
        elif element.tag == "ActivitySummary":
            found.summary(element)
        elif element.tag == "Me":
            found.me(element)
        if element.tag in ("Record", "Workout", "ActivitySummary"):
            element.clear()
    return found


def open_export(path: Path) -> IO[bytes]:
    if path.suffix == ".zip":
        archive = zipfile.ZipFile(path)
        name = next(
            n
            for n in archive.namelist()
            if n.count("/") == 1 and n.endswith(".xml") and not n.endswith("_cda.xml")
        )
        return archive.open(name)
    return path.open("rb")


def post(body: object, token: str, url: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "user-agent": "arga-apple-health-history",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


def send(found: Collected, token: str, url: str) -> None:
    if found.profile:
        print(f"  ficha: {post({'profile': found.profile}, token, url)}")
    items = [{"date": day, **values} for day, values in found.days().items()]
    for start in range(0, len(items), BATCH):
        batch = items[start : start + BATCH]
        print(f"  {batch[0]['date']} … {batch[-1]['date']}: {post(batch, token, url)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Apple Health step counts to OpenArga.")
    parser.add_argument("export", type=Path, help="export.zip o export.xml de Apple Salud")
    parser.add_argument("--dry-run", action="store_true", help="no manda nada")
    parser.add_argument("--url", default=URL)
    arguments = parser.parse_args()

    with open_export(arguments.export) as source:
        found = collect(source)
    days = found.days()
    if not days:
        print("el export no trae nada que Vitals guarde", file=sys.stderr)
        return 1
    stepped = [day for day, values in days.items() if "steps" in values]
    print(f"{len(days)} días, del {min(days)} al {max(days)}; {len(stepped)} con pasos")
    keys = sorted({key for values in days.values() for key in values})
    print(f"cifras: {', '.join(keys)}")
    print(f"ficha: {', '.join(sorted(found.profile)) or 'nada'}")
    if arguments.dry_run:
        return 0
    token = os.environ.get("ARGA_INGEST_TOKEN", "").strip()
    if not token:
        print("falta ARGA_INGEST_TOKEN: el token de Apple Salud en Hub", file=sys.stderr)
        return 1
    send(found, token, arguments.url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
