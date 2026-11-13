from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from arga_module import preferences
from library import library

LATE = datetime(2026, 11, 13, 2, 30, tzinfo=UTC)


class Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return LATE.astimezone(tz)


@pytest.mark.parametrize(
    ("zone", "day"),
    [("Europe/Madrid", date(2026, 11, 13)), ("America/New_York", date(2026, 11, 12))],
)
def test_today_is_the_day_in_the_instance_zone(monkeypatch, zone: str, day: date) -> None:
    monkeypatch.setattr(library, "datetime", Frozen)
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)

    assert library.today() == day


def test_in_a_request_today_is_the_day_in_the_person_zone(monkeypatch) -> None:
    monkeypatch.setattr(library, "datetime", Frozen)
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Europe/Madrid")

    token = preferences.use(preferences.from_headers({"x-arga-timezone": "America/New_York"}))
    try:
        assert library.today() == date(2026, 11, 12)
    finally:
        preferences.reset(token)
