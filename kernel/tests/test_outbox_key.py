from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from arga_testing import fresh_modules
from arga_testing import manifests as repo_manifests
from kernel.db import engine

REPO = Path(__file__).resolve().parents[2]
OWNER = "00000000-0000-4000-8000-0000000000ff"

COMMON = [
    ({"record": {"id": "reading:1"}}, "record", "record:reading:1"),
    ({"metric": {"key": "steps", "day": "2026-10-23"}}, "metric", "metric:steps@2026-10-23"),
    ({"agenda": {"uid": "abc@arga"}}, "agenda", "agenda:abc@arga"),
    ({"something": "else"}, "other", None),
]
TRAVEL = [
    ({"trip_id": "t1", "agenda": {"uid": "x"}}, "trip", "trip:t1"),
    ({"leg_id": "l1", "trip_id": "t1", "agenda": {"uid": "y"}}, "leg", "leg:l1"),
    ({"block_id": "b1", "trip_id": "t1"}, "block", "block:b1"),
    ({"plan_id": "p1", "trip": {}}, "plan", "plan:p1"),
]


@pytest.fixture
async def outboxes(database_url: str) -> list[str]:
    manifests = repo_manifests(REPO / "modules")
    async with engine().begin() as connection:
        await fresh_modules(connection, *(m.id for m in manifests))
        found = (
            await connection.execute(
                text(
                    "select table_schema from information_schema.tables "
                    "where table_name = table_schema || '_outbox' order by 1"
                )
            )
        ).scalars()
        return list(found)


async def test_every_outbox_says_what_each_row_is_about(outboxes: list[str]) -> None:
    assert len(outboxes) >= 14
    wrong = []
    async with engine().connect() as connection:
        transaction = await connection.begin()
        for app in outboxes:
            cases = COMMON + (TRAVEL if app == "travel" else [])
            for number, (payload, kind, expected) in enumerate(cases):
                key = await connection.scalar(
                    text(
                        f"insert into {app}.{app}_outbox (type, ts, payload, dedup_hash, user_id) "
                        "values (:type, now(), cast(:payload as jsonb), :dedup, :owner) "
                        "returning key"
                    ),
                    {
                        "type": f"{app}.{kind}",
                        "payload": json.dumps(payload),
                        "dedup": f"test:{number}",
                        "owner": OWNER,
                    },
                )
                if key != expected:
                    wrong.append(f"{app}.{kind}: {key!r}, no {expected!r}")
        await transaction.rollback()
    assert not wrong, "\n".join(wrong)
