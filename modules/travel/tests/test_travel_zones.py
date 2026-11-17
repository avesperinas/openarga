from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from test_travel_agenda import outbox

import arga_agenda
from travel import travel, zones

AHEAD, BEHIND = "Pacific/Kiritimati", "Pacific/Pago_Pago"


@pytest.mark.parametrize("zone", [AHEAD, BEHIND])
def test_today_is_the_person_s_day(monkeypatch: pytest.MonkeyPatch, zone: str) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)

    assert travel.today() == datetime.now(ZoneInfo(zone)).date()


async def test_a_trip_is_under_way_on_the_person_s_day(api) -> None:
    day = datetime.now(ZoneInfo(AHEAD)).date().isoformat()
    created = await api.post(
        "/trips",
        json={"title": "Islands", "starts_on": day, "ends_on": day, "status": "confirmed"},
        headers={"x-arga-timezone": AHEAD},
    )
    assert created.status_code == 201, created.text

    phases = {}
    for zone in (AHEAD, BEHIND):
        found = await api.get(f"/trips/{created.json()['id']}", headers={"x-arga-timezone": zone})
        phases[zone] = found.json()["phase"]

    assert phases == {AHEAD: "ongoing", BEHIND: "upcoming"}


async def test_the_calendar_gets_the_person_s_zone(api, schema) -> None:
    created = await api.post(
        "/trips",
        json={"title": "Islands", "starts_on": "2025-04-10", "ends_on": "2025-04-12"},
        headers={"x-arga-timezone": BEHIND},
    )
    assert created.status_code == 201, created.text

    item = arga_agenda.check_event((await outbox(schema))[-1])
    assert item["tz"] == BEHIND


@pytest.mark.parametrize("zone", [AHEAD, BEHIND])
def test_a_place_without_its_zone_falls_back_to_the_person_s(
    monkeypatch: pytest.MonkeyPatch, zone: str
) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)

    assert zones.zone_of(None, None, None) == zone
