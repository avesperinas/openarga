from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from test_planner_events import MADRID, at, create

from planner import notices
from planner.db import engine

NOW = datetime(2026, 9, 29, 8, 0, tzinfo=MADRID)


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_planner"'))
        found = await notices.build(connection, NOW)
    return {one["title"]: one for one in found}


async def test_each_own_event_warns_fifteen_minutes_before(api) -> None:
    await create(
        api,
        title="Dentist",
        start=at("2026-09-29T16:00"),
        end=at("2026-09-29T17:30"),
        location="Clinic",
    )
    await create(api, title="Holiday", all_day=True, start="2026-09-30", end="2026-10-01")
    await create(api, title="Lejos", start=at("2026-10-07T10:00"), end=at("2026-10-07T11:00"))
    work = (
        await api.post("/calendars", json={"name": "Trabajo", "tone": 5, "display": "background"})
    ).json()
    await create(
        api,
        title="Jornada",
        calendar_id=work["id"],
        start=at("2026-09-29T09:00"),
        end=at("2026-09-29T14:00"),
    )

    found = await built()

    assert sorted(found) == ["Dentist", "Holiday"]
    dentista = datetime.fromisoformat(found["Dentist"]["at"]).astimezone(MADRID)
    assert dentista.strftime("%H:%M") == "15:45"
    assert found["Dentist"]["body"] == "At 16:00 · Clinic"
    assert found["Dentist"]["href"] == "/planner/day/2026-09-29"
    fiesta = datetime.fromisoformat(found["Holiday"]["at"]).astimezone(MADRID)
    assert fiesta.strftime("%Y-%m-%d %H:%M") == "2026-09-30 09:00"
