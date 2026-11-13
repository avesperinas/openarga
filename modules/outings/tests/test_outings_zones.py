from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from outings_world import make_wish
from sqlalchemy import text

from arga_module import preferences
from outings import agenda, common, metrics, wishes
from outings.db import engine

LATE = datetime(2026, 11, 13, 2, 30, tzinfo=UTC)
ZONES = [("Europe/Madrid", date(2026, 11, 13)), ("America/New_York", date(2026, 11, 12))]


def test_the_zone_is_the_person_s_in_a_request_and_the_instance_s_otherwise(monkeypatch) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", "Asia/Tokyo")
    assert common.zone().key == "Asia/Tokyo"

    token = preferences.use(preferences.from_headers({"x-arga-timezone": "America/New_York"}))
    try:
        assert common.zone().key == "America/New_York"
    finally:
        preferences.reset(token)


@pytest.mark.parametrize(("zone", "day"), ZONES)
def test_a_wish_is_done_on_the_day_of_its_zone(monkeypatch, zone: str, day: date) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)

    assert wishes.done_day(SimpleNamespace(done_at=LATE)) == day


@pytest.mark.parametrize("zone", ["Europe/Madrid", "America/New_York"])
def test_a_plan_goes_to_planner_in_its_zone(monkeypatch, zone: str) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)
    found = SimpleNamespace(
        id="e1",
        title="Synthetic concert",
        venue="Hall",
        town=None,
        time="20:00",
        starts_on=date(2026, 12, 1),
        ends_on=date(2026, 12, 1),
    )

    dated = agenda._dated(found)

    assert dated["tz"] == zone
    assert dated["start"].startswith("2026-12-01T20:00")


@pytest.mark.parametrize(("zone", "day"), ZONES)
async def test_the_wishes_done_metric_counts_by_the_day_of_its_zone(
    api, monkeypatch, zone: str, day: date
) -> None:
    monkeypatch.setenv("OPENARGA_TIMEZONE", zone)
    wish = await make_wish(api, "Late night walk")
    await api.post(f"/wishes/{wish['id']}/done")
    async with engine().begin() as connection:
        await connection.execute(
            text("update outings.outings_wish set done_at = :at where id = cast(:id as uuid)"),
            {"at": LATE, "id": wish["id"]},
        )

    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_outings"'))
        [metric] = await metrics.build(connection)

    assert metric["day"] == day.isoformat() and metric["value"] == 1
