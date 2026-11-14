from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from insights import craft, passes, tastes
from insights.main import as_role

AHEAD, BEHIND = "Pacific/Kiritimati", "Pacific/Pago_Pago"
PILL = (
    "insert into insights.insights_pill (day, origin, family_key, topic, minutes, headline, lead, "
    "sections, to_tell, sources) values (:day, 'daily', 'history', 'a topic', 15, "
    "'A test headline', 'A test lead that is long enough', "
    '\'[{"title": "a", "text": "b"}, {"title": "c", "text": "d"}]\', '
    '\'A test fact to tell someone\', \'[{"title": "x", "url": "https://x.org"}]\')'
)


async def test_today_s_pill_is_the_one_of_the_person_s_day(api) -> None:
    day = datetime.now(ZoneInfo(AHEAD)).date()
    async with as_role("mod_insights") as connection:
        await connection.execute(text(PILL), {"day": day})

    counts = {}
    for zone in (AHEAD, BEHIND):
        response = await api.get("/badge", headers={"x-arga-timezone": zone})
        assert response.status_code == 200, response.text
        counts[zone] = response.json()["count"]

    assert counts == {AHEAD: 1, BEHIND: 0}


@pytest.mark.parametrize(
    ("zone", "morning"), [("Europe/Madrid", True), ("America/New_York", False)]
)
def test_the_morning_pass_follows_the_zone(
    monkeypatch: pytest.MonkeyPatch, zone: str, morning: bool
) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)
    eight_in_madrid = datetime(2026, 10, 13, 7, 0, tzinfo=UTC)

    kinds = [kind for kind, _ in passes.due(eight_in_madrid)]

    assert ("morning" in kinds) is morning


@pytest.mark.parametrize("zone", [AHEAD, BEHIND])
def test_the_pill_is_due_on_the_person_s_morning(
    monkeypatch: pytest.MonkeyPatch, zone: str
) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)
    nine = datetime(2026, 11, 10, 9, 0, tzinfo=ZoneInfo(zone))

    due = dict(craft.due(nine, tastes.Settings(), True))
    early = dict(craft.due(nine - timedelta(hours=3), tastes.Settings(), True))

    assert due["pill"] == "pill:2026-11-10"
    assert "pill" not in early
