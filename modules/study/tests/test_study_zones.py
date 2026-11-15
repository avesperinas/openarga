from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from study import studies

AHEAD, BEHIND = "Pacific/Kiritimati", "Pacific/Pago_Pago"


async def _course(api, headers: dict[str, str]) -> str:
    created = await api.post(
        "/courses",
        json={"name": "A course", "tone": 3, "subjects": [{"name": "A subject"}]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["course"]["id"]


async def test_a_course_takes_the_person_s_zone_by_default(api) -> None:
    course_id = await _course(api, {"x-arga-timezone": AHEAD})

    detail = (await api.get(f"/courses/{course_id}", headers={"x-arga-timezone": AHEAD})).json()

    assert detail["course"]["tz"] == AHEAD


async def test_today_s_week_follows_the_person_s_day(api) -> None:
    course_id = await _course(api, {"x-arga-timezone": AHEAD})
    ahead_day = datetime.now(ZoneInfo(AHEAD)).date()
    at = datetime.combine(ahead_day, time(10), tzinfo=ZoneInfo(AHEAD))
    added = await api.post(
        f"/courses/{course_id}/sessions",
        json={
            "kind": "event",
            "title": "A talk",
            "starts_at": at.isoformat(),
            "ends_at": (at + timedelta(hours=1)).isoformat(),
        },
        headers={"x-arga-timezone": AHEAD},
    )
    assert added.status_code == 201, added.text

    seen = {}
    for zone in (AHEAD, BEHIND):
        week = (await api.get("/home", headers={"x-arga-timezone": zone})).json()
        seen[zone] = [one["date"] for one in week["days"] if one["sessions"]]

    assert seen[AHEAD] == [ahead_day.isoformat()]


@pytest.mark.parametrize("zone", [AHEAD, BEHIND])
def test_today_is_the_person_s_day(monkeypatch: pytest.MonkeyPatch, zone: str) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)

    assert studies.today() == datetime.now(ZoneInfo(zone)).date()
