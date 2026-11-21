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


async def owned_rows(engine, cast) -> dict[str, int]:
    demo = script()
    values = {"people": [person.id for person in cast.people], "space": cast.space_id}
    found = {}
    async with engine.connect() as connection:
        owned = {row.name: row.shared for row in await connection.execute(demo.OWNED)}
        for name, shared in sorted(owned.items()):
            mine = "user_id = any(:people)" + (" or space_id = :space" if shared else "")
            found[name] = await connection.scalar(
                text(f"select count(*) from {name} where {mine}"), values
            )
    return found


async def test_copies_sit_beside_the_cast_whole_and_one_drops_alone(empty) -> None:
    demo = script()
    await demo.run("seed", TODAY, URL)
    engine = install(create_async_engine(URL))
    first = second = None
    try:
        first, made = await demo.make_copy(engine, "copyaaa1", "es", TODAY)
        second, other = await demo.make_copy(engine, "copybbb2", "en", TODAY)
        base = await owned_rows(engine, CAST)

        assert made.failed == {} and other.failed == {}
        assert await owned_rows(engine, first) == base
        assert await owned_rows(engine, second) == base

        await demo.drop_copy(engine, first)

        assert sum((await owned_rows(engine, first)).values()) == 0
        assert await owned_rows(engine, second) == base
        assert await owned_rows(engine, CAST) == base
        async with engine.connect() as connection:
            left = await connection.scalar(
                text("select count(*) from kernel.users where id = any(:ids)"),
                {"ids": [person.id for person in first.people]},
            )
        assert left == 0
    finally:
        for cast in (first, second):
            if cast is not None:
                await demo.drop_copy(engine, cast)
        await engine.dispose()


async def test_a_copy_speaks_the_language_it_was_made_in(empty) -> None:
    from arga_module.i18n import t

    folder = ROOT / "modules" / "insights" / "src" / "insights" / "i18n"
    demo = script()
    engine = install(create_async_engine(URL))
    try:
        cast, report = await demo.make_copy(engine, "copyccc3", "es", TODAY)
        alex = cast.people[0]
        async with engine.connect() as connection:
            name = await connection.scalar(
                text(
                    "select name from insights.insights_family "
                    "where key = 'history' and user_id = :u"
                ),
                {"u": alex.id},
            )
        await demo.drop_copy(engine, cast)
    finally:
        await engine.dispose()

    assert report.failed == {}
    assert alex.key == "alex" and alex.locale == "es"
    assert name == t(folder, "family.history.name", "es")


async def test_the_cast_itself_is_never_dropped_as_a_copy() -> None:
    with pytest.raises(ValueError):
        await script().drop_copy(None, CAST)


async def registry(engine) -> dict[str, tuple[str, str]]:
    async with engine.connect() as connection:
        rows = await connection.execute(text("select tag, locale, status from kernel.demo_copies"))
        return {row.tag: (row.locale, row.status) for row in rows}


async def test_the_keeper_fills_the_pool_and_drops_what_nobody_uses(empty, monkeypatch) -> None:
    demo = script()
    monkeypatch.setenv("OPENARGA_DEMO_POOL", "1")
    monkeypatch.setenv("OPENARGA_DEMO_COPIES_MAX", "4")
    engine = install(create_async_engine(URL))
    try:
        first = await demo.keep(engine, TODAY)
        made = await registry(engine)

        assert first.failed == {} and len(first.made) == 2
        assert sorted(made.values()) == [("en", "ready"), ("es", "ready")]

        old = next(tag for tag, (locale, _) in made.items() if locale == "en")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "update kernel.demo_copies set status = 'claimed', "
                    "claimed_at = now() - interval '3 hours' where tag = :tag"
                ),
                {"tag": old},
            )
        stray, _ = await demo.make_copy(engine, "strayzz9", "en", TODAY)

        second = await demo.keep(engine, TODAY)
        after = await registry(engine)

        assert sorted(second.dropped) == sorted([old, "strayzz9"])
        assert len(second.made) == 1 and second.failed == {}
        assert old not in after and "strayzz9" not in after
        assert sorted(after.values()) == [("en", "ready"), ("es", "ready")]
        assert sum((await owned_rows(engine, cast_of.copy_of(CAST, old))).values()) == 0
        assert sum((await owned_rows(engine, stray)).values()) == 0
    finally:
        for tag in await registry(engine):
            await demo.drop_copy(engine, cast_of.copy_of(CAST, tag))
        async with engine.begin() as connection:
            await connection.execute(text("delete from kernel.demo_copies"))
        await engine.dispose()


async def test_the_keeper_stops_at_the_cap(empty, monkeypatch) -> None:
    demo = script()
    monkeypatch.setenv("OPENARGA_DEMO_POOL", "3")
    monkeypatch.setenv("OPENARGA_DEMO_COPIES_MAX", "1")
    engine = install(create_async_engine(URL))
    try:
        kept = await demo.keep(engine, TODAY)

        assert len(kept.made) == 1
        assert len(await registry(engine)) == 1
    finally:
        for tag in await registry(engine):
            await demo.drop_copy(engine, cast_of.copy_of(CAST, tag))
        async with engine.begin() as connection:
            await connection.execute(text("delete from kernel.demo_copies"))
        await engine.dispose()


def test_reset_refuses_while_visitors_have_copies(monkeypatch) -> None:
    demo = script()
    monkeypatch.setenv("OPENARGA_DEMO", "true")
    monkeypatch.setenv("OPENARGA_DEMO_COPIES", "true")
    monkeypatch.setattr("sys.argv", ["demo.py", "reset"])

    assert demo.main() == 1


def test_keep_refuses_without_copies(monkeypatch) -> None:
    demo = script()
    monkeypatch.setenv("OPENARGA_DEMO", "true")
    monkeypatch.delenv("OPENARGA_DEMO_COPIES", raising=False)
    monkeypatch.setattr("sys.argv", ["demo.py", "keep"])

    assert demo.main() == 1
