from __future__ import annotations

from datetime import datetime, timedelta

from test_vitals_google import log  # noqa: F401 - el fixture del log, compartido
from test_vitals_v2 import DAY, as_vitals, gym, heart_day, profile_of_age, workout  # noqa: F401

from vitals import night, sleep, steps, workouts
from vitals.steps import MADRID


def test_a_full_night_is_a_hundred() -> None:
    found = sleep.score(480, {"deep": 100, "rem": 120, "light": 260, "awake": 20}, None)

    assert found is not None
    assert (found.value, found.quality) == (100, "excellent")
    assert (found.duration, found.depth, found.calm) == (50, 25, 25)


def test_each_part_counts_what_it_says() -> None:
    found = sleep.score(360, {"deep": 40, "rem": 50, "light": 270, "awake": 40}, None)

    assert found is not None
    assert (found.duration, found.depth, found.calm) == (37.5, 13.9, 18.7)
    assert (found.value, found.quality) == (70, "fair")


def test_without_stages_it_is_the_duration_over_a_hundred() -> None:
    found = sleep.score(432, None, None)

    assert found is not None
    assert (found.value, found.depth, found.calm) == (90, None, None)
    assert sleep.score(0, None, None) is None


async def night_of(log, woke, start: str, end: str, asleep: int, **extra) -> None:  # noqa: F811
    await log(
        {
            "id": f"night:{woke.isoformat()}",
            "date": woke.isoformat(),
            "start": start,
            "end": end,
            "minutes_asleep": asleep,
            **extra,
        },
        f"{woke.isoformat()}T08:00:00+00:00",
        "health.sleep",
    )


async def test_a_night_with_its_pulse_its_neighbours_and_its_score(schema, log) -> None:  # noqa: F811
    woke = steps.today() - timedelta(days=1)
    eve = woke - timedelta(days=1)
    midnight = datetime.combine(woke, datetime.min.time(), MADRID)
    for back, day in ((2, eve), (0, woke)):
        start = midnight - timedelta(days=back // 2, minutes=60)
        await night_of(
            log,
            day,
            start.isoformat(),
            (start + timedelta(hours=8)).isoformat(),
            450,
            stages={"deep": 80, "rem": 100, "light": 270, "awake": 20},
            segments=[
                {
                    "start": start.isoformat(),
                    "end": (start + timedelta(hours=1)).isoformat(),
                    "stage": "light",
                }
            ],
        )
    await heart_day(log, eve, {23 * 60: 58, 23 * 60 + 30: 55, 20 * 60: 80})
    await heart_day(log, woke, {3 * 60: 50, 12 * 60: 90})

    found = await as_vitals(schema, night.page, woke)

    assert found is not None
    assert [(one.at.hour, one.bpm) for one in found.heart] == [(23, 58), (23, 55), (3, 50)]
    assert (found.previous, found.next) == (eve, None)
    assert found.night.score is not None and found.night.score.value == 94
    assert found.mean_30.nights == 1
    assert len(found.night.segments) == 1
    assert await as_vitals(schema, night.page, woke - timedelta(days=5)) is None


async def test_each_week_counts_its_minutes_in_each_zone(schema, gym, log) -> None:  # noqa: F811
    await profile_of_age(log, 40)
    await heart_day(log, DAY, {19 * 60 + m: 100 for m in range(0, 30)})
    await gym(workout("w:z", DAY, "19:00", "19:30"))

    found = await as_vitals(schema, workouts.load, 2)

    [week] = [one for one in found.weeks if one.workouts]
    assert week.zones == [30.0, 0.0, 0.0, 0.0, 0.0]


async def test_the_heart_of_a_workout_only_for_the_app_that_published_it(
    schema,
    gym,  # noqa: F811
    log,  # noqa: F811
    api,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "el-token")
    await profile_of_age(log, 40)
    await heart_day(log, DAY, {19 * 60 + m: 130 for m in range(0, 30)})
    await gym(workout("probe_gym:padel", DAY, "19:00", "19:30"))
    kernel = {"x-module-token": "el-token", "x-arga-module": "probe_gym"}

    refused = await api.post("/capabilities/workout.heart", json={"id": "probe_gym:padel"})
    other = await api.post(
        "/capabilities/workout.heart",
        json={"id": "probe_gym:padel"},
        headers={**kernel, "x-arga-module": "training"},
    )
    found = await api.post(
        "/capabilities/workout.heart", json={"id": "probe_gym:padel"}, headers=kernel
    )
    missing = await api.post(
        "/capabilities/workout.heart", json={"id": "probe_gym:nada"}, headers=kernel
    )

    assert refused.status_code == 401
    assert other.status_code == 403
    body = found.json()
    assert (body["found"], body["minutes"], body["avg"], body["max_heart_rate"]) == (
        True,
        30,
        130,
        180,
    )
    assert body["zones"][2] == 30
    assert body["source"] == "day"
    assert missing.json()["found"] is False


async def test_the_sleep_widget_is_the_score_of_the_last_night(schema, log) -> None:  # noqa: F811
    from arga_widgets import validate
    from vitals import widgets

    woke = steps.today()
    start = datetime.combine(woke, datetime.min.time(), MADRID) - timedelta(hours=1)
    await night_of(
        log,
        woke,
        start.isoformat(),
        (start + timedelta(hours=8)).isoformat(),
        450,
        stages={"deep": 80, "rem": 100, "light": 270, "awake": 20},
    )

    found = await as_vitals(schema, widgets.sleep_score)

    assert found["state"] == "ready"
    assert (found["body"]["value"], found["body"]["target"]) == (94, 100)
    assert found["body"]["label"].startswith("excelente · 7 h 30")
    validate("ring", found["body"])


async def test_the_week_widget_counts_workouts_time_and_hard_minutes(schema, gym, log) -> None:  # noqa: F811
    from vitals import widgets

    await profile_of_age(log, 40)
    today = steps.today()
    await heart_day(log, today, {7 * 60 + m: 130 for m in range(0, 45)})
    await gym(workout("w:week", today, "07:00", "07:45"))

    found = await as_vitals(schema, widgets.training_week)

    assert found["state"] == "ready"
    stats = {one["label"]: one["value"] for one in found["body"]["stats"]}
    assert (stats["Entrenos"], stats["Tiempo"], stats["Zona 3+"]) == (1, "0 h 45", 45)


def test_falling_asleep_counts_the_awake_start_of_the_night() -> None:
    at = "2026-10-14T00:{:02d}:00+02:00"
    segments = [
        {"start": at.format(0), "end": at.format(8), "stage": "awake"},
        {"start": at.format(8), "end": at.format(30), "stage": "light"},
        {"start": at.format(30), "end": at.format(35), "stage": "awake"},
    ]

    assert sleep.fell_asleep_after(0, segments) == 8
    assert sleep.fell_asleep_after(12, segments) == 12
    assert sleep.fell_asleep_after(None, []) is None
    assert sleep.fell_asleep_after(None, segments[1:]) == 0
