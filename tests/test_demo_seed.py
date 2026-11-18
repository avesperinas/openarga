from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date
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


def test_reset_refuses_outside_a_demo_instance(monkeypatch) -> None:
    demo = script()
    monkeypatch.delenv("OPENARGA_DEMO", raising=False)
    monkeypatch.setattr("sys.argv", ["demo.py", "reset"])

    assert demo.main() == 1
