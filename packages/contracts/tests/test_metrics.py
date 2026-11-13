from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import arga_contracts as contracts
from arga_contracts import metrics
from arga_contracts.records import OUTBOX_KEY

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://openarga:changeme@localhost:5433/openarga"
)
APP = "zzmetrics"


def steps(day: int, value: float) -> dict:
    return contracts.metric(
        APP,
        key=f"{APP}.steps",
        label="Pasos",
        unit="steps",
        kind="amount",
        day=date(2026, 10, day),
        value=value,
    )


def weight(day: int, value: float) -> dict:
    return contracts.metric(
        APP,
        key=f"{APP}.weight",
        label="Peso",
        unit="kg",
        kind="level",
        day=date(2026, 10, day),
        value=value,
    )


@pytest.fixture
async def outbox():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text(f"drop schema if exists {APP} cascade"))
        await connection.execute(text(f"create schema {APP}"))
        await connection.execute(
            text(
                f"create table {APP}.{APP}_outbox ("
                "  id bigint generated always as identity primary key,"
                "  type text not null, ts timestamptz not null default now(),"
                "  payload jsonb not null, dedup_hash text not null,"
                "  published_at timestamptz,"
                "  user_id uuid not null default '00000000-0000-0000-0000-000000000001',"
                f"  key text generated always as ({OUTBOX_KEY}) stored,"
                "  unique (user_id, dedup_hash))"
            )
        )
    yield engine
    async with engine.begin() as connection:
        await connection.execute(text(f"drop schema if exists {APP} cascade"))
    await engine.dispose()


async def queued(engine) -> list[tuple[str, str, float]]:
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                text(f"select type, payload from {APP}.{APP}_outbox order by id")
            )
        ).all()
    for row in rows:
        assert row.type == f"{APP}.metric"
    return [
        (row.payload["metric"]["key"], row.payload["metric"]["day"], row.payload["metric"]["value"])
        for row in rows
    ]


async def test_the_history_goes_once_and_only_what_changed_after(outbox) -> None:
    everything = [steps(1, 6120), steps(2, 9000), weight(1, 80)]
    async with outbox.begin() as connection:
        first = await metrics.publish(connection, APP, everything)
    assert first == {"added": 3, "changed": 0, "zeroed": 0}
    async with outbox.begin() as connection:
        again = await metrics.publish(connection, APP, everything)
    assert again == {"added": 0, "changed": 0, "zeroed": 0}
    async with outbox.begin() as connection:
        later = await metrics.publish(connection, APP, [steps(1, 8340), *everything[1:]])
    assert later == {"added": 0, "changed": 1, "zeroed": 0}
    assert (await queued(outbox))[-1] == (f"{APP}.steps", "2026-10-01", 8340)


async def test_an_amount_left_empty_says_zero_and_a_level_stays(outbox) -> None:
    async with outbox.begin() as connection:
        await metrics.publish(connection, APP, [steps(1, 6120), weight(1, 80)])
    async with outbox.begin() as connection:
        gone = await metrics.publish(connection, APP, [])
    assert gone == {"added": 0, "changed": 0, "zeroed": 1}
    assert (await queued(outbox))[-1] == (f"{APP}.steps", "2026-10-01", 0)
    async with outbox.begin() as connection:
        assert await metrics.publish(connection, APP, []) == {"added": 0, "changed": 0, "zeroed": 0}


async def test_going_back_to_a_value_of_before_is_a_new_event(outbox) -> None:
    for value in (6120, 8340, 6120):
        async with outbox.begin() as connection:
            await metrics.publish(connection, APP, [steps(1, value)])
    assert [one[2] for one in await queued(outbox)] == [6120, 8340, 6120]


async def test_the_same_point_twice_is_a_bug_of_whoever_builds_them(outbox) -> None:
    async with outbox.begin() as connection:
        with pytest.raises(contracts.BadContract, match="repeated"):
            await metrics.publish(connection, APP, [steps(1, 1), steps(1, 2)])


async def test_a_steady_level_keeps_the_day_it_changed(outbox) -> None:
    async with outbox.begin() as connection:
        await metrics.publish(connection, APP, [weight(1, 80)])
    async with outbox.begin() as connection:
        same = await metrics.steady(connection, APP, [weight(5, 80)])
        moved = await metrics.steady(connection, APP, [weight(5, 79)])
    assert same[0]["day"] == "2026-10-01"
    assert moved[0]["day"] == "2026-10-05"
