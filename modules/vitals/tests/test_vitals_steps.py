from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text

from vitals import steps

OTHER = UUID("00000000-0000-4000-8000-00000000b0b0")
KERNEL_LIKE = "kernel_as_in_production"

INSERT = text("""
    insert into kernel.events (ts, ingested_at, module, source, type, payload, dedup_hash, user_id)
    values (:ts, :received, 'hub', 'apple_health', :type, cast(:payload as jsonb), :dedup,
            :user)
""")


@pytest.fixture
async def log(schema, person):
    written = []
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

    async def send(day: str, count: int, received: str, user: UUID = person, kind="health.steps"):
        async with schema.begin() as connection:
            await connection.execute(
                INSERT,
                {
                    "ts": datetime.fromisoformat(f"{day}T12:00:00+00:00"),
                    "received": datetime.fromisoformat(received),
                    "type": kind,
                    "payload": json.dumps({"date": day, "steps": count}),
                    "dedup": f"steps:{day}:{count}:{user}",
                    "user": user,
                },
            )
        written.append(day)

    yield send
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where source = 'apple_health'"))


def day(text_: str, count: int) -> steps.StepsDay:
    return steps.StepsDay(day=date.fromisoformat(text_), steps=count)


def test_the_streak_counts_days_over_the_goal_and_today_does_not_break_it() -> None:
    days = [
        day("2026-09-20", 9000),
        day("2026-09-21", 8000),
        day("2026-09-22", 12000),
        day("2026-09-23", 8500),
        day("2026-09-24", 3000),
    ]

    assert steps.streak(days, 8000, date(2026, 9, 24)) == 4
    assert steps.streak(days[:4], 8000, date(2026, 9, 24)) == 4
    assert steps.streak(days[:4], 8000, date(2026, 9, 23)) == 4
    assert steps.streak(days, None, date(2026, 9, 24)) == 0


def test_means_count_only_days_with_data() -> None:
    days = [day("2026-09-20", 6000), day("2026-09-24", 10000)]

    summary = steps.summarise(days, 8000, None, date(2026, 9, 24))

    assert summary.mean_7 == 8000
    assert summary.today == days[1]
    assert summary.best == days[1]
    assert summary.by_weekday[3] == 10000
    assert summary.by_weekday[0] is None


def test_weeks_and_months_add_up() -> None:
    days = [day("2026-08-31", 1000), day("2026-09-01", 2000), day("2026-09-07", 3000)]

    weeks = steps.buckets(days, "week")
    months = steps.buckets(days, "month")

    assert [(one.start.isoformat(), one.total, one.days) for one in weeks] == [
        ("2026-08-31", 3000, 2),
        ("2026-09-07", 3000, 1),
    ]
    assert [(one.start.isoformat(), one.total) for one in months] == [
        ("2026-08-01", 1000),
        ("2026-09-01", 5000),
    ]


async def test_the_same_day_sent_twice_keeps_the_last_received(api, log) -> None:
    await log("2026-09-24", 7400, "2026-09-24T21:30:00+00:00")
    await log("2026-09-24", 11200, "2026-09-25T07:00:00+00:00")
    await log("2026-09-23", 9900, "2026-09-23T21:30:00+00:00")
    await log("2026-09-23", 9800, "2026-09-24T07:00:00+00:00")

    found = (await api.get("/steps")).json()

    assert [(one["day"], one["steps"]) for one in found["days"]] == [
        ("2026-09-23", 9800),
        ("2026-09-24", 11200),
    ]
    assert found["last_received"].startswith("2026-09-25T07:00")


async def test_someone_elses_steps_and_other_events_are_not_seen(api, log) -> None:
    await log("2026-09-24", 5000, "2026-09-24T21:30:00+00:00", user=OTHER)
    await log("2026-09-24", 5000, "2026-09-24T21:30:00+00:00", kind="finance.balance")

    assert (await api.get("/steps")).json()["days"] == []


async def test_the_goal_comes_from_settings(api, log) -> None:
    await api.put("/goals", json={"steps_per_day": 8000})
    today = steps.today()
    for back in range(3):
        one = (today - timedelta(days=back)).isoformat()
        await log(one, 9000, f"{one}T21:30:00+00:00")

    found = (await api.get("/steps")).json()

    assert found["goal"] == 8000
    assert found["streak"] == 3
    assert found["mean_7"] == 9000


async def test_the_summary_mean_leaves_today_out(api, log) -> None:
    today = steps.today()
    await log(today.isoformat(), 1000, f"{today.isoformat()}T09:00:00+00:00")
    for back in range(1, 8):
        one = (today - timedelta(days=back)).isoformat()
        await log(one, 7000 + back * 100, f"{one}T21:30:00+00:00")
    old = (today - timedelta(days=8)).isoformat()
    await log(old, 50000, f"{old}T21:30:00+00:00")

    found = (await api.get("/kpis")).json()["steps"]

    assert found["mean_7_past"] == 7400
    assert found["mean_7"] != found["mean_7_past"]
