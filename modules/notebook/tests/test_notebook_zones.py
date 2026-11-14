from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from notebook import digest

AHEAD, BEHIND = "Pacific/Kiritimati", "Pacific/Pago_Pago"


async def test_today_s_note_is_the_day_of_the_person_s_zone(api) -> None:
    titles = {}
    for zone in (AHEAD, BEHIND):
        response = await api.post("/daily", headers={"x-arga-timezone": zone})
        assert response.status_code in (200, 201), response.text
        titles[zone] = response.json()["title"]

    assert titles[AHEAD] == datetime.now(ZoneInfo(AHEAD)).date().isoformat()
    ahead, behind = (datetime.fromisoformat(titles[z]).date() for z in (AHEAD, BEHIND))
    assert ahead - behind == timedelta(days=1)


@pytest.mark.parametrize(("zone", "closed"), [("Europe/Madrid", True), ("America/New_York", False)])
def test_the_week_closes_at_six_in_the_morning_of_the_zone(
    monkeypatch: pytest.MonkeyPatch, zone: str, closed: bool
) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)
    monday = datetime(2026, 10, 12, 5, 30, tzinfo=UTC)

    titles = [period.title for period in digest.due(monday)]

    assert ("2026-W41" in titles) is closed
