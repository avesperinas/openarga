from __future__ import annotations

from datetime import UTC, datetime

from outings import weekly


def test_monday_before_six_is_still_last_week() -> None:
    assert weekly.key(datetime(2026, 10, 12, 3, 30, tzinfo=UTC)) is None
    assert weekly.key(datetime(2026, 10, 12, 4, 0, tzinfo=UTC)) == "agenda:2026-W42"


def test_the_rest_of_the_week_asks_for_the_same_week() -> None:
    thursday = weekly.key(datetime(2026, 10, 15, 18, 0, tzinfo=UTC))
    sunday = weekly.key(datetime(2026, 10, 18, 21, 0, tzinfo=UTC))

    assert thursday == sunday == "agenda:2026-W42"


def test_it_asks_at_most_once_an_hour_per_person() -> None:
    weekly.ASKED.clear()

    assert weekly.due("ana", clock=1000.0) is True
    assert weekly.due("ana", clock=1000.0 + 1800) is False
    assert weekly.due("luis", clock=1000.0 + 1800) is True
    assert weekly.due("ana", clock=1000.0 + 3600) is True
