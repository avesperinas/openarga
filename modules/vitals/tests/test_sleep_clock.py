from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from vitals import sleep


def test_the_hour_of_a_night_is_the_one_on_the_person_s_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sleep, "zone", lambda: ZoneInfo("Europe/Madrid"))

    assert sleep.clock(datetime(2026, 11, 19, 6, 30, tzinfo=UTC)) == 7 * 60 + 30
    assert sleep.clock(datetime(2026, 11, 18, 22, 0, tzinfo=UTC)) == 23 * 60 - 1440
    assert sleep.clock(datetime(2026, 11, 19, 7, 30)) == 7 * 60 + 30
    tokyo = ZoneInfo("Asia/Tokyo")
    assert sleep.clock(datetime(2026, 11, 19, 7, 30, tzinfo=tokyo)) == 7 * 60 + 30
