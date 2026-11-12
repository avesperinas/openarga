from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "apple-health-steps.py"
spec = importlib.util.spec_from_file_location("apple_health_steps", SCRIPT)
assert spec and spec.loader
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)

EXPORT = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="es_ES">
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
   startDate="2026-09-23 08:00:00 +0200" endDate="2026-09-23 08:10:00 +0200" value="1200"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
   startDate="2026-09-23 19:00:00 +0200" endDate="2026-09-23 19:30:00 +0200" value="3000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Reloj" unit="count"
   startDate="2026-09-23 08:00:00 +0200" endDate="2026-09-23 08:10:00 +0200" value="1300"/>
 <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Bascula" unit="kg"
   startDate="2026-09-23 07:00:00 +0200" endDate="2026-09-23 07:00:00 +0200" value="80"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Reloj" unit="count"
   startDate="2026-09-24 23:50:00 +0200" endDate="2026-09-24 23:59:00 +0200" value="800.4"/>
</HealthData>
"""


def test_each_day_is_the_source_that_counted_most_not_the_sum() -> None:
    days = history.per_day(history.records(io.BytesIO(EXPORT)))

    assert days == {"2026-09-23": 4200, "2026-09-24": 800}


def test_it_reads_the_zip_as_it_comes_from_the_phone(tmp_path: Path) -> None:
    exported = tmp_path / "export.zip"
    with zipfile.ZipFile(exported, "w") as archive:
        archive.writestr("apple_health_export/export.xml", EXPORT)

    with history.open_export(exported) as source:
        assert history.per_day(history.records(source))["2026-09-23"] == 4200


FULL = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="es_ES">
 <Me HKCharacteristicTypeIdentifierDateOfBirth="1990-01-01"
   HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"
   HKCharacteristicTypeIdentifierBloodType="HKBloodTypeONegative"
   HKCharacteristicTypeIdentifierFitzpatrickSkinType="HKFitzpatrickSkinTypeNotSet"
   HKCharacteristicTypeIdentifierCardioFitnessMedicationsUse="Ninguna"/>
 <Record type="HKQuantityTypeIdentifierHeight" sourceName="iPhone" unit="cm"
   startDate="2018-01-08 10:00:00 +0100" endDate="2018-01-08 10:00:00 +0100" value="170"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Reloj" unit="count/min"
   startDate="2026-09-23 08:00:00 +0200" endDate="2026-09-23 08:00:00 +0200" value="60"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Reloj" unit="count/min"
   startDate="2026-09-23 18:00:00 +0200" endDate="2026-09-23 18:00:00 +0200" value="120"/>
 <Record type="HKQuantityTypeIdentifierWalkingAsymmetryPercentage" sourceName="iPhone" unit="%"
   startDate="2026-09-23 18:00:00 +0200" endDate="2026-09-23 18:00:00 +0200" value="0.05"/>
 <Record type="HKQuantityTypeIdentifierActiveEnergyBurned" sourceName="Reloj" unit="kcal"
   startDate="2026-09-23 09:00:00 +0200" endDate="2026-09-23 09:30:00 +0200" value="100.5"/>
 <Record type="HKQuantityTypeIdentifierActiveEnergyBurned" sourceName="iPhone" unit="kcal"
   startDate="2026-09-23 09:00:00 +0200" endDate="2026-09-23 09:30:00 +0200" value="80"/>
 <Record type="HKCategoryTypeIdentifierAppleStandHour" sourceName="Reloj"
   startDate="2026-09-23 09:00:00 +0200" endDate="2026-09-23 10:00:00 +0200"
   value="HKCategoryValueAppleStandHourStood"/>
 <Record type="HKCategoryTypeIdentifierAppleStandHour" sourceName="Reloj"
   startDate="2026-09-23 10:00:00 +0200" endDate="2026-09-23 11:00:00 +0200"
   value="HKCategoryValueAppleStandHourIdle"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Reloj"
   startDate="2026-09-23 23:00:00 +0200" endDate="2026-09-24 03:00:00 +0200"
   value="HKCategoryValueSleepAnalysisAsleepUnspecified"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Reloj"
   startDate="2026-09-24 02:00:00 +0200" endDate="2026-09-24 07:00:00 +0200"
   value="HKCategoryValueSleepAnalysisAsleepUnspecified"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="iPhone"
   startDate="2026-09-23 22:30:00 +0200" endDate="2026-09-24 07:30:00 +0200"
   value="HKCategoryValueSleepAnalysisInBed"/>
 <Record type="HKCategoryTypeIdentifierSexualActivity" sourceName="iPhone"
   startDate="2026-09-23 22:00:00 +0200" endDate="2026-09-23 22:00:00 +0200"
   value="HKCategoryValueNotApplicable"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30"
   startDate="2026-09-23 07:00:00 +0200" endDate="2026-09-23 07:30:00 +0200"/>
 <ActivitySummary dateComponents="2026-09-23" activeEnergyBurnedGoal="500"
   appleExerciseTimeGoal="30" appleStandHoursGoal="12"/>
</HealthData>
"""


def test_it_reads_every_figure_vitals_keeps_and_nothing_else() -> None:
    found = history.collect(io.BytesIO(FULL))

    assert found.days() == {
        "2026-09-23": {
            "active_kcal": 100.5,
            "heart_rate_min": 60.0,
            "heart_rate_avg": 90.0,
            "heart_rate_max": 120.0,
            "asymmetry_pct": 5.0,
            "stand_hours": 1,
            "move_goal_kcal": 500.0,
            "exercise_goal_min": 30.0,
            "stand_goal_hours": 12.0,
        },
        "2026-09-24": {"sleep_min": 480, "in_bed_min": 540},
    }
    assert found.profile == {
        "height_cm": 170.0,
        "blood_type": "0-",
        "sex": "female",
        "birth_date": "1990-01-01",
        "cardio_medications": "Ninguna",
    }


def test_it_finds_the_export_with_its_spanish_name(tmp_path: Path) -> None:
    exported = tmp_path / "exportación.zip"
    with zipfile.ZipFile(exported, "w") as archive:
        archive.writestr("apple_health_export/export_cda.xml", b"<ClinicalDocument/>")
        archive.writestr("apple_health_export/exportación.xml", EXPORT)
        archive.writestr("apple_health_export/workout-routes/route.gpx", b"<gpx/>")

    with history.open_export(exported) as source:
        assert history.collect(source).days()["2026-09-23"] == {"steps": 4200}


SPANNING = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="es_ES">
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
   startDate="2018-10-02 12:00:00 +0200" endDate="2018-10-04 12:00:00 +0200" value="48000"/>
 <Record type="HKQuantityTypeIdentifierDistanceWalkingRunning" sourceName="iPhone" unit="km"
   startDate="2018-10-02 12:00:00 +0200" endDate="2018-10-04 12:00:00 +0200" value="36"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count"
   startDate="2018-10-04 18:00:00 +0200" endDate="2018-10-04 18:10:00 +0200" value="1000"/>
</HealthData>
"""


def test_a_sample_spanning_days_is_shared_by_the_hours_of_each_not_piled_on_its_first() -> None:
    days = history.collect(io.BytesIO(SPANNING)).days()

    assert {day: values["steps"] for day, values in days.items()} == {
        "2018-10-02": 12000,
        "2018-10-03": 24000,
        "2018-10-04": 13000,
    }
    assert [values["distance_km"] for values in days.values()] == [9.0, 18.0, 9.0]
    assert history.per_day(history.records(io.BytesIO(SPANNING))) == {
        "2018-10-02": 12000,
        "2018-10-03": 24000,
        "2018-10-04": 13000,
    }
