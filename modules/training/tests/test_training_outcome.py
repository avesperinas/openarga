from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_tenancy import install
from training import db, seed
from training.main import MODULE_ID, app
from training.outcome import new_records

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime.now(UTC).replace(hour=17, minute=0, second=0, microsecond=0) - timedelta(days=20)


def test_a_record_is_more_load_in_the_same_rep_range() -> None:
    found = new_records([(8, 62.5), (8, 60)], [(8, 60), (10, 57.5)])

    assert found == [("6-10", 8, 62.5, 60)]


def test_the_first_time_in_a_range_is_not_a_record() -> None:
    assert new_records([(5, 70)], [(8, 60)]) == []


def test_matching_the_best_is_not_a_record() -> None:
    assert new_records([(8, 60)], [(8, 60)]) == []


def test_each_range_counts_on_its_own() -> None:
    found = new_records([(3, 80), (12, 40)], [(5, 75), (15, 45), (8, 60)])

    assert found == [("1-5", 3, 80, 75)]


@pytest.fixture
async def api(database_url: str):
    from arga_testing import fresh_modules

    engine = install(create_async_engine(database_url))
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from kernel.events where module = :m"), {"m": MODULE_ID}
        )
        await fresh_modules(connection, MODULE_ID, root=ROOT)
        await connection.execute(text('set local role "mod_training"'))
        await seed.seed(connection)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as client:
        yield client
    async with engine.begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": MODULE_ID})
        await connection.execute(
            text("delete from kernel.events where module = :m"), {"m": MODULE_ID}
        )
    await engine.dispose()
    await db.engine().dispose()
    db.engine.cache_clear()


async def push(api, offset: int, weight: str, finish: bool = True) -> tuple[str, dict]:
    days = (await api.get("/today")).json()["plan"]["days"]
    day = next(day for day in days if day["kind"] == "push")
    started = T0 + timedelta(days=offset)
    session = (
        await api.post(
            "/sessions", json={"started_at": started.isoformat(), "plan_day_id": day["id"]}
        )
    ).json()["id"]
    slot = day["slots"][0]
    exercise = (
        await api.post(
            f"/sessions/{session}/exercises",
            json={"plan_slot_id": slot["id"], "variant_id": slot["options"][0]["variant_id"]},
        )
    ).json()["id"]
    for number in (1, 2):
        await api.put(
            f"/sessions/{session}/exercises/{exercise}/sets/{number}",
            json={"reps": 8, "weight": weight, "confirmed_at": started.isoformat()},
        )
    if finish:
        ended = started + timedelta(hours=1)
        await api.post(f"/sessions/{session}/finish", json={"ended_at": ended.isoformat()})
    return session, slot


async def test_a_session_says_what_it_worked_and_what_it_beat(api) -> None:
    await push(api, 0, "60")
    session, slot = await push(api, 7, "62.5")

    outcome = (await api.get(f"/sessions/{session}/outcome")).json()

    assert [
        (r["variant_id"], r["range"], r["load"], r["previous"]) for r in outcome["records"]
    ] == [(slot["options"][0]["variant_id"], "6-10", 62.5, 60.0)]
    assert outcome["muscles"][0]["sets"] == 2.0


async def test_the_first_session_has_no_records(api) -> None:
    session, _ = await push(api, 0, "60")

    outcome = (await api.get(f"/sessions/{session}/outcome")).json()

    assert outcome["records"] == []
    assert outcome["muscles"]


async def test_a_running_session_shows_its_work_but_no_records_yet(api) -> None:
    await push(api, 0, "60")
    session, _ = await push(api, 7, "62.5", finish=False)

    outcome = (await api.get(f"/sessions/{session}/outcome")).json()

    assert outcome["records"] == []
    assert outcome["muscles"]


async def test_an_unknown_session_is_a_404(api) -> None:
    response = await api.get("/sessions/00000000-0000-4000-8000-000000000000/outcome")

    assert response.status_code == 404
