from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from test_vitals_google import INSERT, log  # noqa: F401 - the shared log fixture

from vitals import labs, notices, records, steps, today, workouts

PROBE = "probe_gym"

MADRID = ZoneInfo("Europe/Madrid")


@pytest.fixture
async def gym(schema, person, log):  # noqa: F811
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:id, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "id": PROBE,
                "manifest": json.dumps(
                    {"publishes": [{"type": f"{PROBE}.workout", "contract": "workout"}]}
                ),
            },
        )
    sent = 0

    async def publish(workout: dict, received: datetime | None = None) -> None:
        nonlocal sent
        sent += 1
        async with schema.begin() as connection:
            await connection.execute(
                text(
                    "insert into kernel.events "
                    "(ts, ingested_at, module, source, type, payload, dedup_hash, user_id) "
                    "values (:ts, :at, :module, 'app', :type, cast(:payload as jsonb), :dedup, "
                    ":user)"
                ),
                {
                    "ts": datetime.fromisoformat(workout["end"]),
                    "at": received or datetime.now(UTC) + timedelta(seconds=sent),
                    "module": PROBE,
                    "type": f"{PROBE}.workout",
                    "payload": json.dumps({"workout": workout}),
                    "dedup": f"workout:{sent}",
                    "user": person,
                },
            )

    yield publish
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": PROBE})
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": PROBE})


async def as_vitals(schema, action, *args):
    async with schema.begin() as connection:
        await connection.execute(text('set local role "mod_vitals"'))
        return await action(connection, *args)


def at(day: date, clock: str) -> str:
    hour, minute = (int(one) for one in clock.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=MADRID).isoformat()


def workout(id_: str, day: date, start: str, end: str, **extra) -> dict:
    return {
        "id": id_,
        "kind": "activity",
        "name": "Padel",
        "start": at(day, start),
        "end": at(day, end),
        "tz": "Europe/Madrid",
        "href": None,
        "band_id": None,
        "marks": [],
        "removed": False,
        **extra,
    }


DAY = steps.today() - timedelta(days=1)


async def heart_day(log, day: date, values: dict[int, float]) -> None:  # noqa: F811
    await log(
        {
            "date": day.isoformat(),
            "step": 1,
            "buckets": [
                {"minute": minute, "min": bpm, "avg": bpm, "max": bpm}
                for minute, bpm in sorted(values.items())
            ],
        },
        f"{day.isoformat()}T23:00:00+00:00",
        "health.heart",
    )


async def profile_of_age(log, age: int) -> None:  # noqa: F811
    born = date(steps.today().year - age, 1, 1).isoformat()
    await log({"birth_date": born}, "2026-01-01T00:00:00+00:00", "health.profile")


async def test_a_workout_the_band_measured_takes_its_fine_heart(schema, gym, log) -> None:  # noqa: F811
    await profile_of_age(log, 40)
    start = at(DAY, "19:00")
    await log(
        {
            "id": "band:1",
            "kind": "PADEL",
            "name": "Padel",
            "start": start,
            "end": at(DAY, "19:10"),
            "kcal": 140.0,
            "heart": [
                {"s": 0, "bpm": 100},
                {"s": 120, "bpm": 130},
                {"s": 360, "bpm": 165},
                {"s": 540, "bpm": 150},
            ],
        },
        f"{DAY.isoformat()}T20:00:00+00:00",
        "health.exercise",
    )
    await heart_day(log, DAY, {19 * 60 + 11: 120, 19 * 60 + 12: 104})
    await gym(workout("w:1", DAY, "19:00", "19:10", band_id="band:1"))

    [found] = await as_vitals(schema, workouts.between, DAY, DAY)

    assert (found.name, found.minutes, found.from_band, found.kcal) == ("Padel", 10, True, 140.0)
    assert found.heart.source == "band"
    assert found.heart.max == 165
    assert found.heart.zones == [2.0, 0.0, 4.0, 1.0, 3.0]
    assert found.heart.load == 2 * 1 + 4 * 3 + 1 * 4 + 3 * 5
    assert found.heart.recovery_2min == 150 - 104

    detail = await as_vitals(schema, workouts.one, "w:1")
    assert detail.max_heart_rate == 180
    assert [one.s for one in detail.beats] == [0, 120, 360, 540, 660, 720]


async def test_without_the_band_it_is_the_heart_of_the_day_in_its_hours(
    schema,
    gym,
    log,  # noqa: F811
) -> None:
    await heart_day(log, DAY, {7 * 60 + m: 90 + m for m in range(-5, 70)})
    marks = [{"at": at(DAY, "07:05"), "label": "Bench press · 8 × 60 kg"}]
    await gym(workout("w:2", DAY, "07:00", "08:00", kind="strength", name="Push", marks=marks))

    [found] = await as_vitals(schema, workouts.between, DAY, DAY)
    detail = await as_vitals(schema, workouts.one, "w:2")

    assert (found.kind, found.heart.source, found.from_band) == ("strength", "day", False)
    assert found.heart.avg == 119.5
    assert detail.beats[0].s == 0 and detail.beats[-1].s == 62 * 60
    assert [one.label for one in detail.marks] == ["Bench press · 8 × 60 kg"]


async def test_what_was_withdrawn_is_gone_and_a_correction_wins(schema, gym) -> None:
    await gym(workout("w:3", DAY, "18:00", "19:00"))
    await gym(workout("w:3", DAY, "18:15", "19:30"))
    await gym(workout("w:4", DAY, "20:00", "21:00"))
    await gym(workout("w:4", DAY, "20:00", "21:00", removed=True))

    found = await as_vitals(schema, workouts.between, DAY, DAY)

    assert [(one.id, one.minutes) for one in found] == [("w:3", 75)]


async def test_the_load_of_this_week_against_the_four_before(schema, gym, log) -> None:  # noqa: F811
    now = steps.today()
    monday = workouts.monday(now)
    await profile_of_age(log, 40)
    for weeks_back in range(1, 5):
        day = monday - timedelta(weeks=weeks_back)
        await heart_day(log, day, {18 * 60 + m: 130 for m in range(0, 60)})
        await gym(workout(f"past:{weeks_back}", day, "18:00", "18:30"))
    await heart_day(log, monday, {18 * 60 + m: 150 for m in range(0, 60)})
    await gym(workout("now", monday, "18:00", "18:20"))

    found = await as_vitals(schema, workouts.load, 12, now)

    assert found.mean_4 == 90.0
    assert found.this_week == 80.0
    assert [one.workouts for one in found.weeks[-5:]] == [1, 1, 1, 1, 1]


async def test_today_against_your_normal(schema, log) -> None:  # noqa: F811
    now = steps.today()
    for back in range(1, 31):
        day = now - timedelta(days=back)
        await log(
            {"date": day.isoformat(), "metrics": {"resting_heart_rate": 55 + back % 3}},
            f"{day.isoformat()}T12:00:00+00:00",
        )
    await log(
        {"date": now.isoformat(), "metrics": {"resting_heart_rate": 64, "spo2_pct": 96}},
        f"{now.isoformat()}T12:00:00+00:00",
    )

    found = await as_vitals(schema, today.read, now)
    by_id = {one.id: one for one in found.baselines}

    assert (by_id["resting_heart_rate"].value, by_id["resting_heart_rate"].status) == (64, "above")
    assert by_id["resting_heart_rate"].mean == 56.0
    assert by_id["resting_heart_rate"].days == 30
    assert (by_id["spo2_pct"].value, by_id["spo2_pct"].status, by_id["spo2_pct"].mean) == (
        96,
        None,
        None,
    )
    assert by_id["hrv_ms"].day is None


async def test_nights_after_training_against_the_rest(schema, gym, log) -> None:  # noqa: F811
    from vitals import patterns

    now = steps.today()
    for back in range(1, 9):
        woke = now - timedelta(days=back)
        trained_before = back % 2 == 0
        if trained_before:
            await gym(workout(f"t:{back}", woke - timedelta(days=1), "20:30", "21:30"))
        start = datetime.combine(woke - timedelta(days=1), datetime.min.time(), MADRID)
        await log(
            {
                "id": f"night:{back}",
                "date": woke.isoformat(),
                "start": (start + timedelta(hours=23)).isoformat(),
                "end": (start + timedelta(hours=31)).isoformat(),
                "minutes_asleep": 420 if trained_before else 450,
                "stages": {"deep": 60, "rem": 90, "light": 270, "awake": 30},
            },
            f"{woke.isoformat()}T08:00:00+00:00",
            "health.sleep",
        )

    found = await as_vitals(schema, patterns.read, now)
    [after, late] = found.comparisons

    assert (after.after.nights, after.after.asleep) == (4, 420)
    assert (after.rest.nights, after.rest.asleep) == (4, 450)
    assert late.after.nights == 4
    assert found.fell_asleep_spread == 0


async def test_the_last_checkup_against_the_one_before(schema, api) -> None:
    old = (await api.post("/checkups", json={"day": "2025-06-11", "center": "A"})).json()["id"]
    new = (await api.post("/checkups", json={"day": "2026-09-02", "center": "A"})).json()["id"]
    for checkup, ldl, hdl in ((old, 120, 50), (new, 150, 52)):
        for analyte, value in (("ldl", ldl), ("hdl", hdl)):
            await api.post(
                f"/checkups/{checkup}/results",
                json={"analyte": analyte, "value": value, "unit": "mg/dL", "ref_high": 130}
                if analyte == "ldl"
                else {"analyte": analyte, "value": value, "unit": "mg/dL", "ref_low": 40},
            )

    found = (await api.get("/labs/changes")).json()

    assert (found["checkup"]["day"], found["previous"]["day"]) == ("2026-09-02", "2025-06-11")
    first = found["changes"][0]
    assert (first["analyte"]["id"], first["previous"], first["value"]) == ("ldl", 120, 150)
    assert (first["out"], first["was_out"]) == (True, False)
    assert [one["analyte"]["id"] for one in found["changes"]] == ["ldl", "hdl"]
    assert isinstance(labs.Changes.model_validate(found), labs.Changes)


async def test_the_band_says_when_it_runs_low_or_stops_syncing(schema, log) -> None:  # noqa: F811
    now = datetime.now(UTC)
    await log(
        {
            "id": "dev:1",
            "name": "Fitbit Air",
            "kind": "tracker",
            "battery_pct": 12,
            "last_sync": (now - timedelta(hours=30)).isoformat(),
        },
        now.isoformat(),
        "health.device",
    )

    found = await as_vitals(schema, notices.build, now)

    assert sorted(one["kind"] for one in found) == ["battery_low", "not_synced"]
    battery = next(one for one in found if one["kind"] == "battery_low")
    assert battery["title"] == "Fitbit Air: low battery at 12 %"


async def test_each_week_is_a_note_for_notebook(schema, gym, log) -> None:  # noqa: F811
    monday = workouts.monday(steps.today())
    await gym(workout("w:week", monday, "12:00", "12:30", name="Cycling"))

    found = await as_vitals(
        schema,
        records.build,
    )
    [week] = [one for one in found if one["id"] == f"week:{monday.isoformat()}"]

    assert week["folder"] == "Weeks"
    assert (week["properties"]["workouts"], week["properties"]["workout_min"]) == (1, 30)
    assert "Cycling · 30 min" in week["body"]


async def test_the_tools_tell_today_and_each_workout(schema, gym, api, log) -> None:  # noqa: F811
    await heart_day(log, DAY, {12 * 60 + m: 120 for m in range(0, 40)})
    await gym(workout("w:tool", DAY, "12:00", "12:30", name="Cycling"))
    headers = {"x-arga-scopes": "vitals:read"}

    listed = (await api.post("/tools/get_workouts", json={}, headers=headers)).json()["content"]
    one = (await api.post("/tools/get_workouts", json={"id": "w:tool"}, headers=headers)).json()[
        "content"
    ]
    now = (await api.post("/tools/get_today", json={}, headers=headers)).json()["content"]

    assert [w["name"] for w in listed["workouts"]] == ["Cycling"]
    assert one["heart_per_minute"][0] == {"minute": 0, "avg": 120, "max": 120}
    assert len(one["heart_per_minute"]) == 33
    assert "status" in now["baselines"][0] and "weeks" not in now["load"]


async def test_a_checkup_gives_the_link_to_attach_its_pdf(api) -> None:
    found = (
        await api.post(
            "/tools/record_checkup",
            json={"date": "2026-10-01", "center": "Laboratorio"},
            headers={"x-arga-scopes": "vitals:write"},
        )
    ).json()["content"]

    assert found["attach_pdf_url"].endswith(f"/vitals/labs?attach={found['checkup_id']}")


async def test_today_brings_the_steps_and_the_last_pulse(schema, log) -> None:  # noqa: F811
    now = steps.today()
    await heart_day(log, now, {9 * 60: 70, 9 * 60 + 1: 74})
    await log(
        {"date": now.isoformat(), "steps": 6240},
        f"{now.isoformat()}T10:00:00+00:00",
        "health.steps",
    )

    found = await as_vitals(schema, today.read, now)

    assert found.steps.today == 6240
    assert (found.pulse.minute, found.pulse.bpm) == (9 * 60 + 1, 74)
