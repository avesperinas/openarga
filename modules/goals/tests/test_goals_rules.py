from __future__ import annotations

from datetime import date, datetime, time

import pytest

from goals.common import MADRID
from goals.tasks import status

AT = datetime(2026, 9, 28, 17, 30, tzinfo=MADRID)


@pytest.mark.parametrize(
    ("due_on", "due_time", "expected"),
    [
        (None, None, "someday"),
        (date(2026, 9, 27), None, "overdue"),
        (date(2026, 9, 28), None, "today"),
        (date(2026, 9, 28), time(9, 0), "overdue"),
        (date(2026, 9, 28), time(18, 0), "today"),
        (date(2026, 9, 29), time(8, 0), "upcoming"),
    ],
)
def test_the_status_depends_on_the_day_and_the_hour(due_on, due_time, expected) -> None:
    assert status(due_on, due_time, None, AT) == expected


def test_done_is_done_whatever_the_date() -> None:
    assert status(date(2026, 1, 1), None, AT, AT) == "done"


def test_the_day_is_madrids() -> None:
    late = datetime(2026, 9, 28, 23, 30, tzinfo=MADRID)
    assert status(date(2026, 9, 28), None, None, late) == "today"
