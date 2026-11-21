from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_module import demo as cast_of
from arga_tenancy import install

ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)
CAST = cast_of.load(ROOT / "demo" / "personas.yaml")
TODAY = date.today()


def script():
    spec = importlib.util.spec_from_file_location("demo_script", ROOT / "scripts" / "demo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def empty():
    from arga_testing import fresh_modules

    os.environ["DATABASE_URL"] = URL
    seeded = list(cast_of.seeds(ROOT / "modules"))
    engine = install(create_async_engine(URL))
    async with engine.begin() as connection:
        await fresh_modules(connection, *seeded)

    yield seeded

    await script().forget(engine, CAST, seeded)
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from kernel.modules where id = any(:ids)"), {"ids": seeded}
        )
    await engine.dispose()


async def rows(modules: list[str]) -> dict[str, int]:
    engine = create_async_engine(URL)
    found = {}
    async with engine.connect() as connection:
        for module_id in modules:
            tables = (
                await connection.execute(
                    text("select tablename from pg_tables where schemaname = :s"), {"s": module_id}
                )
            ).scalars()
            total = 0
            for table in tables:
                total += await connection.scalar(
                    text(f'select count(*) from "{module_id}"."{table}"')
                )
            found[module_id] = total
        found["people"] = await connection.scalar(
            text("select count(*) from kernel.space_members where space_id = :s"),
            {"s": CAST.space_id},
        )
    await engine.dispose()
    return found


async def test_one_command_fills_an_empty_instance_and_runs_again_the_same(empty) -> None:
    demo = script()

    first = await demo.run("seed", TODAY, URL)
    counted = await rows(empty)
    again = await demo.run("seed", TODAY, URL)

    assert first.failed == {} and sorted(first.seeded) == sorted(empty)
    assert again.failed == {}
    assert counted["people"] == len(CAST.people)
    assert all(counted[module_id] > 0 for module_id in empty), counted
    assert await rows(empty) == counted


async def test_a_simulated_day_and_a_reset_leave_a_full_demo(empty) -> None:
    demo = script()
    await demo.run("seed", TODAY, URL)

    day = await demo.run("day", TODAY, URL)
    reset = await demo.run("reset", TODAY, URL)

    assert day.failed == {} and reset.failed == {}
    counted = await rows(empty)
    assert all(counted[module_id] > 0 for module_id in empty), counted
    assert counted["people"] == len(CAST.people)


async def test_the_health_feed_reaches_today_and_never_repeats(empty) -> None:
    demo = script()
    engine = create_async_engine(URL)
    query = text("""
        select type, count(*) as n, min((payload->>'date')::date) as first,
               max((payload->>'date')::date) as last
        from kernel.events where source = 'google_health' and user_id = :user
        group by type
    """)

    async def feed() -> dict[str, dict[str, tuple]]:
        async with engine.connect() as connection:
            return {
                person.key: {
                    row.type: (row.n, row.first, row.last)
                    for row in await connection.execute(query, {"user": person.id})
                }
                for person in CAST.people
            }

    await demo.run("seed", TODAY, URL)
    first = await feed()
    await demo.run("seed", TODAY, URL)
    await demo.run("day", TODAY, URL)
    again = await feed()
    await engine.dispose()

    assert first == again
    for person in first.values():
        for kind in ("health.steps", "health.daily", "health.sleep", "health.heart"):
            assert person[kind][2] == TODAY, kind
        assert (TODAY - person["health.steps"][1]).days >= 530
        assert person["health.exercise"][0] >= 40


async def test_the_next_day_adds_a_day_and_nothing_breaks(empty) -> None:
    demo = script()
    tomorrow = TODAY + timedelta(days=1)
    await demo.run("seed", TODAY, URL)
    before = await rows(empty)

    day = await demo.run("day", tomorrow, URL)
    after = await rows(empty)

    assert day.failed == {}
    assert sorted(day.seeded) == sorted(empty)
    assert all(after[module_id] >= before[module_id] for module_id in empty), (before, after)
    engine = create_async_engine(URL)
    async with engine.connect() as connection:
        newest = await connection.scalar(
            text(
                "select max((payload->>'date')::date) from kernel.events "
                "where source = 'google_health' and type = 'health.steps'"
            )
        )
    await engine.dispose()
    assert newest == tomorrow


def test_reset_refuses_outside_a_demo_instance(monkeypatch) -> None:
    demo = script()
    monkeypatch.delenv("OPENARGA_DEMO", raising=False)
    monkeypatch.setattr("sys.argv", ["demo.py", "reset"])

    assert demo.main() == 1


async def test_what_an_app_names_by_itself_comes_in_each_person_s_language(empty) -> None:
    from arga_module.i18n import t

    folder = ROOT / "modules" / "insights" / "src" / "insights" / "i18n"
    engine = create_async_engine(URL)
    await script().run("seed", TODAY, URL)
    async with engine.connect() as connection:
        names = {
            person.key: await connection.scalar(
                text(
                    "select name from insights.insights_family "
                    "where key = 'history' and user_id = :u"
                ),
                {"u": person.id},
            )
            for person in CAST.people
        }
    await engine.dispose()

    assert names["alex"] == t(folder, "family.history.name", "en")
    assert names["sam"] == t(folder, "family.history.name", "es")
    assert names["alex"] != names["sam"]


def test_today_is_the_cast_s_day_not_the_server_s() -> None:
    from datetime import UTC, datetime

    late_in_utc = datetime(2026, 11, 20, 23, 30, tzinfo=UTC)
    assert script().cast_today(CAST, late_in_utc) == date(2026, 11, 21)
