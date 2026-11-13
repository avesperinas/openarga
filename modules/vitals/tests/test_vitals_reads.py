from __future__ import annotations

import asyncio
import re
from datetime import UTC, date, datetime, timedelta

from test_vitals_google import at, day, log  # noqa: F401 - the shared log fixture
from test_vitals_v2 import DAY, as_vitals, gym, heart_day, profile_of_age, workout  # noqa: F401

from vitals import body, memo, sleep, steps, today, workouts


def figure_of(overview: dict, metric: str) -> dict:
    return next(
        figure
        for section in overview["sections"]
        for figure in section["figures"]
        if figure["id"] == metric
    )


async def test_many_versions_of_a_day_give_the_last_one(api, log) -> None:  # noqa: F811
    for n, kcal in enumerate((120, 260, 410, 535)):
        await log(
            {"date": day(1), "metrics": {"active_kcal": kcal, "resting_heart_rate": 58 - n}},
            at(1, f"1{n}:15"),
        )
    await log({"date": day(2), "metrics": {"active_kcal": 300}}, at(2, "10:00"))

    kcal = (await api.get("/body/active_kcal")).json()
    overview = (await api.get("/body")).json()

    assert [(one["day"], one["value"]) for one in kcal["points"]] == [
        (day(2), 300.0),
        (day(1), 535.0),
    ]
    resting = figure_of(overview, "resting_heart_rate")
    assert (resting["latest"]["value"], resting["days"]) == (55.0, 1)


async def test_an_earlier_version_keeps_what_the_last_one_does_not_bring(schema, log) -> None:  # noqa: F811
    await log({"date": day(1), "metrics": {"vo2max": 45, "resting_heart_rate": 60}}, at(1, "08:00"))
    await log({"date": day(1), "metrics": {"active_kcal": 90, "vo2max": 46}}, at(1, "09:00"))
    await log({"date": day(1), "metrics": {"resting_heart_rate": 57}}, at(1, "10:00"))

    found = await as_vitals(schema, body.read)

    assert {
        key: [(one.day.isoformat(), one.value) for one in points] for key, points in found.items()
    } == {
        "vo2max": [(day(1), 46.0)],
        "resting_heart_rate": [(day(1), 57.0)],
        "active_kcal": [(day(1), 90.0)],
    }


async def test_two_sources_and_the_switch_stay_as_they_were(api, log) -> None:  # noqa: F811
    await log({"date": day(40), "steps": 7000}, at(40), "health.steps", "apple_health")
    await log(
        {"date": day(40), "metrics": {"resting_heart_rate": 62, "hrv_ms": 80}},
        at(40),
        source="apple_health",
    )
    for clock, (resting, hrv, walked) in (("08:00", (56, 40, 8000)), ("09:00", (55, 41, 9000))):
        await log(
            {"date": day(1), "metrics": {"resting_heart_rate": resting, "hrv_ms": hrv}},
            at(1, clock),
        )
        await log({"date": day(1), "steps": walked}, at(1, clock), "health.steps")
    await log(
        {
            "date": day(1),
            "metrics": {"resting_heart_rate": 61, "hrv_ms": 70, "walking_speed_kmh": 4.6},
        },
        at(1, "21:00"),
        source="apple_health",
    )
    await log({"date": day(1), "steps": 12000}, at(1, "21:00"), "health.steps", "apple_health")

    resting = (await api.get("/body/resting_heart_rate")).json()
    walking = (await api.get("/body/walking_speed_kmh")).json()
    overview = (await api.get("/body")).json()
    walked = (await api.get("/steps")).json()

    assert [(one["day"], one["value"]) for one in resting["points"]] == [
        (day(40), 62.0),
        (day(1), 55.0),
    ]
    assert [(one["day"], one["value"]) for one in walking["points"]] == [(day(1), 4.6)]
    hrv = figure_of(overview, "hrv_ms")
    assert (hrv["latest"]["value"], hrv["changed_on"], hrv["mean_30"]) == (41.0, day(1), 41.0)
    assert [(one["day"], one["steps"]) for one in walked["days"]] == [
        (day(40), 7000),
        (day(1), 9000),
    ]
    assert walked["last_received"].startswith(f"{day(1)}T09:00")


async def test_baselines_ignore_what_is_older_than_a_year_but_see_what_is_inside(
    api,
    schema,
    log,  # noqa: F811
) -> None:
    now = steps.today()
    for back in range(1, 31):
        await log({"date": day(back), "metrics": {"resting_heart_rate": 55 + back % 3}}, at(back))
    await log({"date": day(0), "metrics": {"resting_heart_rate": 64}}, at(0))

    normal = await as_vitals(schema, today.baselines, now)
    year = figure_of((await api.get("/body")).json(), "resting_heart_rate")

    await log({"date": day(400), "metrics": {"resting_heart_rate": 90}}, at(400))
    await log(
        {"date": day(420), "metrics": {"resting_heart_rate": 95, "walking_speed_kmh": 4.1}},
        at(0, "06:00"),
        source="apple_health",
    )

    memo.forget()
    assert await as_vitals(schema, today.baselines, now) == normal
    overview = (await api.get("/body")).json()
    later = figure_of(overview, "resting_heart_rate")
    assert (later["mean_30"], later["mean_365"]) == (year["mean_30"], year["mean_365"])
    assert later["days"] == year["days"] + 2
    sections = {one["id"]: one for one in overview["sections"]}
    assert [(f["id"], f["latest"]["day"]) for f in sections["history"]["figures"]] == [
        ("walking_speed_kmh", day(420))
    ]

    await log({"date": day(10), "metrics": {"resting_heart_rate": 80}}, at(10, "23:00"))
    await log({"date": day(300), "metrics": {"resting_heart_rate": 70}}, at(300))

    memo.forget()
    moved = {one.id: one for one in await as_vitals(schema, today.baselines, now)}
    still = {one.id: one for one in normal}
    assert moved["resting_heart_rate"].mean != still["resting_heart_rate"].mean
    assert moved["resting_heart_rate"].days == still["resting_heart_rate"].days
    inside = figure_of((await api.get("/body")).json(), "resting_heart_rate")
    assert inside["mean_365"] != year["mean_365"]


async def test_your_normal_reads_only_what_arrived_since_the_last_visit(
    schema,
    log,  # noqa: F811
    monkeypatch,
) -> None:
    now = steps.today()
    for back in range(1, 31):
        await log({"date": day(back), "metrics": {"resting_heart_rate": 55 + back % 3}}, at(back))
    await log({"date": day(0), "metrics": {"resting_heart_rate": 64}}, at(0, "07:00"))
    read: list[tuple] = []
    whole = body.raw

    async def counted(connection, since, until):
        read.append((since, until))
        return await whole(connection, since, until)

    monkeypatch.setattr(body, "raw", counted)

    first = await as_vitals(schema, today.baselines, now)
    again = await as_vitals(schema, today.baselines, now)
    await log({"date": day(5), "metrics": {"resting_heart_rate": 90}}, at(0, "08:00"))
    later = {one.id: one for one in await as_vitals(schema, today.baselines, now)}

    assert again == first
    five = now - timedelta(days=5)
    assert read == [(now - timedelta(days=today.WINDOW + 1), date.max), (now, now), (five, now)]
    before = {one.id: one for one in first}
    assert later["resting_heart_rate"].mean != before["resting_heart_rate"].mean
    memo.forget()
    assert await as_vitals(schema, today.baselines, now) == list(later.values())


async def test_an_activity_published_days_before_it_happens_is_there(schema, gym) -> None:  # noqa: F811
    soon = steps.today() + timedelta(days=5)
    await gym(workout("w:antes", soon, "18:00", "19:00"), received=datetime.now(UTC))

    found = await as_vitals(schema, workouts.between, soon, soon)

    assert [one.id for one in found] == ["w:antes"]


async def test_two_workouts_at_the_same_time_keep_their_order(schema, gym) -> None:  # noqa: F811
    for name in ("w:b", "w:a", "w:c"):
        await gym(workout(name, DAY, "18:00", "19:00"))

    first = [one.id for one in await as_vitals(schema, workouts.between, DAY, DAY)]
    memo.forget()
    again = [one.id for one in await as_vitals(schema, workouts.between, DAY, DAY)]

    assert first == again == ["w:a", "w:b", "w:c"]


async def test_the_band_traces_are_not_kept_only_their_versions(schema, gym, log) -> None:  # noqa: F811
    done = workout("w:1", DAY, "18:00", "18:30", band_id="band:1")
    await log(
        {
            "id": "band:1",
            "kind": "PADEL",
            "name": "Padel",
            "start": done["start"],
            "end": done["end"],
            "heart": [{"s": 0, "bpm": 120}, {"s": 600, "bpm": 140}],
        },
        at(1, "19:00"),
        "health.exercise",
    )
    await gym(done)

    found = await as_vitals(schema, workouts.between, DAY, DAY)
    kept = memo.get("exercises")

    assert found[0].from_band and found[0].heart.avg == 130.0
    assert set(kept.found) == {"band:1"}
    assert not hasattr(kept.found["band:1"], "payload")


async def test_what_is_kept_is_read_whole_again_after_a_while(schema, log, monkeypatch) -> None:  # noqa: F811
    now = steps.today()
    await log({"date": day(1), "metrics": {"resting_heart_rate": 55}}, at(1))
    read: list[tuple] = []
    whole = body.raw

    async def counted(connection, since, until):
        read.append((since, until))
        return await whole(connection, since, until)

    monkeypatch.setattr(body, "raw", counted)
    await as_vitals(schema, body.read, None, now - timedelta(days=10))
    monkeypatch.setattr(memo, "FULL_EVERY", 0.0)
    await as_vitals(schema, body.read, None, now - timedelta(days=10))

    assert read == [(now - timedelta(days=10), date.max)] * 2


async def test_a_reader_without_sources_does_not_undo_the_choice_of_the_others(
    schema,
    log,  # noqa: F811
    monkeypatch,
) -> None:
    for back in range(1, 6):
        await log({"date": day(back), "metrics": {"resting_heart_rate": 55}}, at(back))
    picked: list = []
    whole = body.pick

    def counted(rows, started):
        picked.append(rows[0].day)
        return whole(rows, started)

    monkeypatch.setattr(body, "pick", counted)
    since = steps.today() - timedelta(days=5)
    await as_vitals(schema, body.read, None, since, date.max, {"google_health": since})
    await as_vitals(schema, body.read, "resting_heart_rate", since)
    await as_vitals(schema, body.read, None, since, date.max, {"google_health": since})

    latest = steps.today() - timedelta(days=1)
    assert sorted(one for one in picked if one != latest) == [
        latest - timedelta(days=n) for n in range(4, 0, -1)
    ]
    assert picked.count(latest) == 3


async def test_a_workout_moved_days_later_keeps_its_band(schema, gym, log) -> None:  # noqa: F811
    before = steps.today() - timedelta(days=6)
    moved = workout("w:movido", DAY, "18:00", "18:30", band_id="band:movido")
    started_at = datetime.fromisoformat(moved["start"]) - timedelta(days=5)
    await log(
        {
            "id": "band:movido",
            "kind": "PADEL",
            "name": "Padel",
            "start": started_at.isoformat(),
            "end": (started_at + timedelta(minutes=30)).isoformat(),
            "heart": [{"s": 0, "bpm": 120}, {"s": 600, "bpm": 140}],
        },
        at(6, "19:00"),
        "health.exercise",
    )
    await gym(workout("w:movido", before, "18:00", "18:30", band_id="band:movido"))
    await gym(moved)

    memo.forget()
    workouts.BUILT.clear()
    found = await as_vitals(schema, workouts.between, DAY, DAY)

    assert [(one.id, one.from_band) for one in found] == [("w:movido", True)]


async def test_workouts_at_the_same_time_keep_their_order_when_one_changes(
    schema,
    gym,  # noqa: F811
) -> None:
    for name in ("w:b", "w:a", "w:c"):
        await gym(workout(name, DAY, "18:30", "19:30"))
    await as_vitals(schema, workouts.between, DAY, DAY)
    await gym(workout("w:a", DAY, "18:30", "19:30", name="Padel edited"))

    again = await as_vitals(schema, workouts.between, DAY, DAY)

    assert [one.id for one in again] == ["w:a", "w:b", "w:c"]
    assert again[0].name == "Padel edited"


async def test_the_heart_of_a_workout_is_the_last_version_that_arrived(
    schema,
    gym,  # noqa: F811
    log,  # noqa: F811
) -> None:
    await gym(workout("w:day", DAY, "18:00", "18:30"))
    await heart_day(log, DAY, {18 * 60 + m: 100 for m in range(0, 30)})
    first = await as_vitals(schema, workouts.between, DAY, DAY)
    await log(
        {
            "date": DAY.isoformat(),
            "step": 1,
            "buckets": [
                {"minute": 18 * 60 + m, "min": 140, "avg": 140, "max": 140} for m in range(0, 30)
            ],
        },
        f"{steps.today().isoformat()}T05:00:00+00:00",
        "health.heart",
    )
    later = await as_vitals(schema, workouts.between, DAY, DAY)

    assert (first[0].heart.avg, later[0].heart.avg) == (100.0, 140.0)


async def test_when_each_source_started_is_read_whole_again_after_a_while(
    schema,
    log,  # noqa: F811
    monkeypatch,
) -> None:
    monkeypatch.setattr(memo, "FULL_EVERY", 0.5)
    await log({"date": day(3), "steps": 7000}, at(3), "health.steps")
    first = await as_vitals(schema, steps.started)
    await log({"date": day(9), "steps": 5000}, at(9), "health.steps", "apple_health")
    missed = await as_vitals(schema, steps.started)
    for _ in range(5):
        await asyncio.sleep(0.2)
        whole = await as_vitals(schema, steps.started)

    assert set(first) == set(missed) == {"google_health"}
    assert set(whole) == {"google_health", "apple_health"}


async def test_a_night_remade_with_another_date_counts_by_the_last(schema, log) -> None:  # noqa: F811
    night = {
        "id": "night-redone",
        "start": f"{day(3)}T23:30:00+02:00",
        "end": f"{day(2)}T07:00:00+02:00",
        "minutes_asleep": 420,
    }
    await log(night | {"date": day(3)}, at(2, "06:00"), "health.sleep")
    await log(night | {"date": day(2), "minutes_asleep": 430}, at(2, "08:00"), "health.sleep")

    assert await as_vitals(schema, sleep.night, steps.today() - timedelta(days=3)) is None
    found = await as_vitals(schema, sleep.night, steps.today() - timedelta(days=2))
    assert found is not None and found.minutes_asleep == 430
    week = await as_vitals(schema, sleep.read, steps.today() - timedelta(days=6))
    assert [(one.day.isoformat(), one.minutes_asleep) for one in week] == [(day(2), 430)]


TODAY_QUERIES = 22
TODAY_QUERIES_AGAIN = 17


async def test_today_answers_with_a_fixed_number_of_queries(api, gym, log) -> None:  # noqa: F811
    now = steps.today()
    await profile_of_age(log, 40)
    for back in range(0, 20):
        for clock, walked in (("09:00", 3000), ("20:00", 9000)):
            await log({"date": day(back), "steps": walked + back}, at(back, clock), "health.steps")
            await log(
                {"date": day(back), "metrics": {"resting_heart_rate": 55, "hrv_ms": 40 + back}},
                at(back, clock),
            )
    await log({"date": day(1), "steps": 12000}, at(1, "21:00"), "health.steps", "apple_health")
    await log(
        {
            "id": "tonight",
            "date": day(0),
            "start": f"{day(1)}T23:30:00+02:00",
            "end": f"{day(0)}T07:00:00+02:00",
            "minutes_asleep": 420,
        },
        at(0, "06:00"),
        "health.sleep",
    )
    await heart_day(log, now, {9 * 60: 70, 9 * 60 + 1: 74})
    await heart_day(log, now - timedelta(days=1), {18 * 60 + m: 130 for m in range(0, 40)})
    await log(
        {
            "id": "band:today",
            "kind": "PADEL",
            "name": "Padel",
            "start": f"{day(1)}T18:00:00+02:00",
            "end": f"{day(1)}T18:30:00+02:00",
            "heart": [{"s": 0, "bpm": 120}, {"s": 600, "bpm": 140}],
        },
        at(1, "19:00"),
        "health.exercise",
    )
    await gym(workout("w:today", now - timedelta(days=1), "18:00", "18:30", band_id="band:today"))

    response = await api.get("/today")
    again = await api.get("/today")

    assert response.status_code == 200
    assert response.json()["steps"]["today"] == 9000
    assert again.json() == response.json()
    for answer, most in ((response, TODAY_QUERIES), (again, TODAY_QUERIES_AGAIN)):
        used = re.search(r'desc="(\d+) consultas"', answer.headers["server-timing"])
        assert used is not None
        assert int(used.group(1)) <= most, answer.headers["server-timing"]
