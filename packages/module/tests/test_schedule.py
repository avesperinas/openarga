from __future__ import annotations

from datetime import UTC, datetime

import pytest

from arga_module.schedule import InvalidSchedule, Schedule


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_once_a_day_at_five() -> None:
    schedule = Schedule.parse("0 5 * * *")

    assert schedule.matches(at("2026-09-22T05:00"))
    assert not schedule.matches(at("2026-09-22T05:01"))
    assert not schedule.matches(at("2026-09-22T17:00"))


def test_every_six_hours_on_the_hour() -> None:
    schedule = Schedule.parse("0 */6 * * *")

    assert schedule.matches(at("2026-09-15T00:00"))
    assert schedule.matches(at("2026-09-15T18:00"))
    assert not schedule.matches(at("2026-09-15T19:00"))


def test_lists_ranges_and_steps() -> None:
    schedule = Schedule.parse("15,45 8-10 * * 1-5")

    assert schedule.matches(at("2026-09-15T09:45"))
    assert not schedule.matches(at("2026-09-19T09:45"))
    assert not schedule.matches(at("2026-09-15T11:15"))


def test_sunday_is_zero_and_seven() -> None:
    assert Schedule.parse("0 9 * * 0").matches(at("2026-09-20T09:00"))
    assert Schedule.parse("0 9 * * 7").matches(at("2026-09-20T09:00"))


def test_with_day_and_weekday_either_one_is_enough() -> None:
    schedule = Schedule.parse("0 9 1 * 1")

    assert schedule.matches(at("2026-10-01T09:00"))
    assert schedule.matches(at("2026-09-21T09:00"))


@pytest.mark.parametrize("expression", ["0 */6 * *", "61 * * * *", "* * * * 8", "a * * * *"])
def test_a_schedule_it_cannot_read_is_refused(expression: str) -> None:
    with pytest.raises(InvalidSchedule):
        Schedule.parse(expression)
