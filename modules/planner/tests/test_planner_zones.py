from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from test_planner_events import create

from planner import notices, widgets
from planner.db import engine

WRITE = {"x-arga-scopes": "planner:read planner:write"}
ZONES = ["Europe/Madrid", "America/New_York"]


@pytest.mark.parametrize("zone", ZONES)
async def test_a_time_without_a_zone_is_in_the_person_s(api, zone: str) -> None:
    response = await api.post(
        "/tools/create_event",
        json={"title": "Call", "start": "2026-10-06T19:00"},
        headers={**WRITE, "x-arga-timezone": zone},
    )

    assert response.status_code == 200, response.text
    created = response.json()["content"]["created"]
    start = datetime.fromisoformat(created["start"]).astimezone(ZoneInfo(zone))
    assert (start.hour, start.minute) == (19, 0)


@pytest.mark.parametrize(
    ("zone", "said"), [("Europe/Madrid", "16:00"), ("America/New_York", "10:00")]
)
async def test_notices_say_the_hour_in_the_instance_zone(
    api, monkeypatch: pytest.MonkeyPatch, zone: str, said: str
) -> None:
    await create(
        api,
        title="Dentist",
        start="2026-09-29T14:00:00+00:00",
        end="2026-09-29T15:00:00+00:00",
    )
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_planner"'))
        found = await notices.build(connection, datetime(2026, 9, 29, 6, 0, tzinfo=UTC))

    [dentist] = found
    assert dentist["body"] == f"At {said}"


@pytest.mark.parametrize(("zone", "shown"), [("Europe/Madrid", ["Lunch"]), ("Asia/Tokyo", [])])
async def test_today_starts_at_midnight_in_the_zone(
    api, monkeypatch: pytest.MonkeyPatch, zone: str, shown: list[str]
) -> None:
    await create(
        api,
        title="Lunch",
        start="2026-09-30T12:00:00+00:00",
        end="2026-09-30T13:00:00+00:00",
    )
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_planner"'))
        found = await widgets.agenda(connection, datetime(2026, 9, 30, 20, 0, tzinfo=UTC))

    assert [one["title"] for one in found["body"]["entries"]] == shown
