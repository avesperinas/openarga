from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from test_vitals_steps import INSERT, KERNEL_LIKE

from vitals import body, steps

OTHER = UUID("00000000-0000-4000-8000-00000000b0b0")


@pytest.fixture
async def log(schema, person):
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists "
                f"(select 1 from pg_roles where rolname = '{KERNEL_LIKE}') "
                f"then create role {KERNEL_LIKE} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.events to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.modules to {KERNEL_LIKE}"))
        await connection.execute(text(f"alter view vitals.events owner to {KERNEL_LIKE}"))
    sent = 0

    async def send(payload: dict, received: str, kind="health.daily", user: UUID = person):
        nonlocal sent
        sent += 1
        async with schema.begin() as connection:
            await connection.execute(
                INSERT,
                {
                    "ts": datetime.fromisoformat(received),
                    "received": datetime.fromisoformat(received),
                    "type": kind,
                    "payload": json.dumps(payload),
                    "dedup": f"{kind}:{sent}:{user}",
                    "user": user,
                },
            )

    yield send
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where source = 'apple_health'"))


def day(back: int) -> str:
    return (steps.today() - timedelta(days=back)).isoformat()


async def test_each_figure_keeps_its_last_value_and_one_send_does_not_erase_another(
    api, log
) -> None:
    await log(
        {"date": day(1), "metrics": {"resting_heart_rate": 60, "active_kcal": 300}},
        f"{day(1)}T21:30:00+00:00",
    )
    await log({"date": day(1), "metrics": {"resting_heart_rate": 57}}, f"{day(0)}T07:00:00+00:00")
    await log({"date": day(0), "metrics": {"resting_heart_rate": 59}}, f"{day(0)}T21:30:00+00:00")

    found = (await api.get("/body")).json()
    heart = next(one for one in found["sections"] if one["id"] == "heart")
    activity = next(one for one in found["sections"] if one["id"] == "activity")
    resting = heart["figures"][0]

    assert resting["id"] == "resting_heart_rate"
    assert resting["latest"] == {"day": day(0), "value": 59.0, "total": None}
    assert resting["mean_30"] == 58.0
    assert resting["days"] == 2
    assert [one["id"] for one in activity["figures"]] == ["active_kcal"]
    assert next(one for one in found["sections"] if one["id"] == "gait")["figures"] == []
    assert found["profile"] is None


async def test_one_figure_day_by_day(api, log) -> None:
    for back, minutes in ((2, 42), (1, 39), (0, 45)):
        await log({"date": day(back), "metrics": {"exercise_min": minutes}}, f"{day(back)}T09:00Z")

    found = (await api.get("/body/exercise_min")).json()

    assert found["figure"]["name"] == "Exercise minutes"
    assert [(one["day"], one["value"]) for one in found["points"]] == [
        (day(2), 42.0),
        (day(1), 39.0),
        (day(0), 45.0),
    ]
    assert (await api.get("/body/sexual_activity")).status_code == 404


async def test_the_profile_is_the_last_value_of_each_field(api, log) -> None:
    await log(
        {"blood_type": "0+", "sex": "female", "birth_date": "1990-01-01"},
        "2026-01-01T12:00:00Z",
        kind="health.profile",
    )
    await log({"blood_type": "0-", "height_cm": 170}, "2026-09-01T12:00:00Z", kind="health.profile")

    profile = (await api.get("/body")).json()["profile"]

    assert profile["blood_type"] == "0-"
    assert profile["sex"] == "female"
    assert profile["height_cm"] == 170
    assert profile["age"] == body.age(date(1990, 1, 1), steps.today())


async def test_someone_elses_figures_are_not_seen(api, log) -> None:
    await log({"date": day(0), "metrics": {"vo2max": 40}}, f"{day(0)}T12:00:00Z", user=OTHER)
    await log({"blood_type": "A+"}, f"{day(0)}T12:00:00Z", kind="health.profile", user=OTHER)

    found = (await api.get("/body")).json()

    assert all(section["figures"] == [] for section in found["sections"])
    assert found["profile"] is None


def test_weeks_give_the_daily_mean_and_the_total_of_what_adds_up() -> None:
    points = [
        body.Point(day=date(2026, 9, 21), value=300),
        body.Point(day=date(2026, 9, 22), value=500),
        body.Point(day=date(2026, 9, 28), value=100),
    ]

    summed = body.grouped(points, "sum", "week")
    last = body.grouped(points, "last", "month")

    assert [(one.day.isoformat(), one.value, one.total) for one in summed] == [
        ("2026-09-21", 400.0, 800.0),
        ("2026-09-28", 100.0, 100.0),
    ]
    assert [(one.day.isoformat(), one.value) for one in last] == [("2026-09-01", 100)]


def test_every_figure_shown_here_is_one_hub_accepts() -> None:
    push = pytest.importorskip("hub.push")
    google = pytest.importorskip("hub.providers.google_health")
    accepted = set(push.METRICS) | set(google.METRICS)

    assert set(body.BY_ID) <= accepted
    assert accepted - set(body.BY_ID) == {"sleep_min", "in_bed_min"}


async def test_sleep_arrives_but_is_not_shown(api, log) -> None:
    await log(
        {"date": day(0), "metrics": {"sleep_min": 420, "respiratory_rate": 14}}, f"{day(0)}T09:00Z"
    )

    found = (await api.get("/body")).json()

    assert [one["id"] for one in found["sections"]] == [
        "heart",
        "activity",
        "breath",
        "gait",
        "more",
        "history",
    ]
    shown = {section["id"]: [f["id"] for f in section["figures"]] for section in found["sections"]}
    assert shown["breath"] == ["respiratory_rate"]
    assert sum(len(ids) for ids in shown.values()) == 1
    assert (await api.get("/body/sleep_min")).status_code == 404


async def test_the_profile_alone_for_the_summary(api, log) -> None:
    assert (await api.get("/profile")).json() is None
    await log({"blood_type": "A+"}, "2026-09-01T12:00:00Z", kind="health.profile")

    assert (await api.get("/profile")).json()["blood_type"] == "A+"


def test_the_weeks_of_a_figure_end_this_week_and_a_week_without_data_is_none() -> None:
    from vitals.body import Point, weekly

    now = date(2026, 11, 5)
    points = [
        Point(day=date(2026, 11, 2), value=60),
        Point(day=date(2026, 11, 4), value=62),
        Point(day=date(2026, 10, 20), value=58),
    ]
    weeks = weekly(points, now, weeks=4)
    assert weeks == [None, 58, None, 61]
    assert len(weekly([], now)) == 26
