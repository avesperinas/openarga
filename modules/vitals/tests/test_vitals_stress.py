from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from test_vitals_google import log  # noqa: F401 - the shared log fixture
from test_vitals_v2 import DAY as YESTERDAY
from test_vitals_v2 import as_vitals, gym, profile_of_age, workout  # noqa: F401

from vitals import steps, stress


def _changes_clock(day) -> bool:
    madrid = ZoneInfo("Europe/Madrid")
    start = datetime.combine(day, time(), madrid).utcoffset()
    return start != datetime.combine(day + timedelta(days=1), time(), madrid).utcoffset()


DAY = YESTERDAY - timedelta(days=1) if _changes_clock(YESTERDAY) else YESTERDAY

SHORT, LONG = date(2026, 3, 29), date(2026, 10, 25)


async def resting(log, value: float, days: int = 30, until: date = DAY) -> None:  # noqa: F811
    for back in range(1, days + 1):
        day = until - timedelta(days=back)
        await log(
            {"date": day.isoformat(), "metrics": {"resting_heart_rate": value}},
            f"{day.isoformat()}T12:00:00+00:00",
        )


async def minutes(log, day, values: dict[int, tuple[float, int]], with_steps=True) -> None:  # noqa: F811
    buckets = []
    for minute, (bpm, walked) in sorted(values.items()):
        one = {"minute": minute, "min": bpm, "avg": bpm, "max": bpm}
        if with_steps:
            one["steps"] = walked
        buckets.append(one)
    await log(
        {"date": day.isoformat(), "step": 1, "buckets": buckets},
        f"{day.isoformat()}T23:00:00+00:00",
        "health.heart",
    )


MADRID = ZoneInfo("Europe/Madrid")


@pytest.mark.parametrize("day", [DAY, SHORT, LONG], ids=["yesterday", "march", "october"])
async def test_only_a_high_pulse_while_still_counts(schema, gym, log, day) -> None:  # noqa: F811
    await profile_of_age(log, 40)
    await resting(log, 60, until=day)
    values = {}
    for m in range(600, 620):
        values[m] = (100, 0)
    for m in range(660, 670):
        values[m] = (110, 80)
    for m in range(670, 675):
        values[m] = (100, 0)
    for m in range(720, 770):
        values[m] = (140, 0)
    for m in range(900, 910):
        values[m] = (80, 0)
    await minutes(log, day, values)
    await gym(workout("w:gym", day, "12:00", "12:30"))

    found = await as_vitals(schema, stress.tension, day)

    tension = found[0]
    assert tension.threshold == 90.0 and tension.resting == 60.0
    assert tension.by_hour[10] == 18 and tension.by_hour[11] == 3
    assert tension.by_hour[12] == 9
    assert tension.minutes == 30


@pytest.mark.parametrize("day", [SHORT, LONG], ids=["march", "october"])
def test_the_minutes_left_out_are_clock_minutes_when_the_clocks_change(day) -> None:

    def clock(on: date, hour: int, minute: int = 0) -> datetime:
        return datetime(on.year, on.month, on.day, hour, minute, tzinfo=MADRID)

    session = tuple(datetime.fromisoformat(clock(day, 12, m).isoformat()) for m in (0, 40))
    night = (clock(day - timedelta(days=1), 23), clock(day, 7).astimezone(UTC))

    assert stress.excluded_minutes(day, [session]) == set(range(720, 761))
    assert stress.excluded_minutes(day, [night]) == set(range(0, 421))


async def test_without_the_steps_of_each_minute_it_says_so(schema, log) -> None:  # noqa: F811
    await resting(log, 60)
    await minutes(log, DAY, {600: (100, 0)}, with_steps=False)

    found, missing = await as_vitals(schema, stress.tension, DAY)

    assert found is None
    assert missing == "this day's heart rate came without the steps of each minute"


async def test_how_you_start_the_day_against_your_normal(schema, log) -> None:  # noqa: F811
    now = steps.today()
    for back in range(1, 31):
        day = now - timedelta(days=back)
        await log(
            {
                "date": day.isoformat(),
                "metrics": {"resting_heart_rate": 58 + back % 3, "hrv_ms": 50 + back % 5},
            },
            f"{day.isoformat()}T12:00:00+00:00",
        )
    await log(
        {"date": now.isoformat(), "metrics": {"resting_heart_rate": 59, "hrv_ms": 52}},
        f"{now.isoformat()}T12:00:00+00:00",
    )

    found = await as_vitals(schema, stress.morning, now)

    assert found.days_left == 0
    assert found.score is not None and 40 <= found.score <= 60


async def test_without_two_weeks_of_band_it_counts_the_days_left(schema, log) -> None:  # noqa: F811
    now = steps.today()
    for back in range(1, 4):
        day = now - timedelta(days=back)
        await log(
            {"date": day.isoformat(), "metrics": {"hrv_ms": 50}},
            f"{day.isoformat()}T12:00:00+00:00",
        )

    found = await as_vitals(schema, stress.morning, now)

    assert (found.score, found.days_left) == (None, 12)
