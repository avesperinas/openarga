from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from arga_contracts import METRIC, BadContract, metric_identity
from arga_contracts.records import Every, _outbox, spaces
from arga_tenancy import as_user

TOLERANCE = 0.005


def last_published(app: str) -> str:
    return (
        f"select distinct on (key) id as row_id, payload->'{METRIC}' as point "
        f"from {_outbox(app)} where type = :type and key like 'metric:%' "
        "order by key, id desc"
    )


def _dedup(point: dict[str, Any], previous: int) -> str:
    said = f"{metric_identity(point)}\n{point['value']}\n{previous}"
    return "metric:" + hashlib.sha256(said.encode()).hexdigest()


def _same(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        abs(float(a["value"]) - float(b["value"])) < TOLERANCE
        and a.get("label") == b.get("label")
        and a.get("unit") == b.get("unit")
        and a.get("kind") == b.get("kind")
    )


LAST_BY_KEY = (
    "select distinct on (payload->'{m}'->>'key') payload->'{m}' as point from {outbox} "
    "where type = :type and payload ? '{m}' "
    "order by payload->'{m}'->>'key', payload->'{m}'->>'day' desc, id desc"
)


async def steady(
    connection: AsyncConnection, app: str, points: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = await connection.execute(
        text(LAST_BY_KEY.format(m=METRIC, outbox=_outbox(app))), {"type": f"{app}.{METRIC}"}
    )
    last = {row.point["key"]: row.point for row in rows.all()}
    out = []
    for point in points:
        before = last.get(point["key"])
        if before is not None and _same(before, point) and before["day"] <= point["day"]:
            point = {**point, "day": before["day"]}
        out.append(point)
    return out


async def publish(
    connection: AsyncConnection, app: str, points: list[dict[str, Any]]
) -> dict[str, int]:
    type_ = f"{app}.{METRIC}"
    now: dict[str, dict[str, Any]] = {}
    for one in points:
        identity = metric_identity(one)
        if identity in now:
            raise BadContract(f"Metric does not match: repeated point: {identity}")
        now[identity] = one
    published = {
        metric_identity(row.point): (row.row_id, row.point)
        for row in (await connection.execute(text(last_published(app)), {"type": type_})).all()
    }
    pending: list[tuple[dict[str, Any], int]] = []
    counts = {"added": 0, "changed": 0, "zeroed": 0}
    for identity, point in now.items():
        before = published.get(identity)
        if before is not None and _same(before[1], point):
            continue
        counts["added" if before is None else "changed"] += 1
        pending.append((point, before[0] if before else 0))
    for identity, (row_id, point) in published.items():
        if identity in now or point.get("kind") != "amount":
            continue
        if abs(float(point["value"])) < TOLERANCE:
            continue
        pending.append(({**point, "value": 0.0}, row_id))
        counts["zeroed"] += 1
    if pending:
        await connection.execute(
            text(
                f"insert into {_outbox(app)} (type, ts, payload, dedup_hash) "
                "values (:type, :ts, cast(:payload as jsonb), :dedup) "
                "on conflict (user_id, dedup_hash) do nothing"
            ),
            [
                {
                    "type": type_,
                    "ts": datetime.now(UTC),
                    "payload": json.dumps({METRIC: point}, ensure_ascii=False),
                    "dedup": _dedup(point, previous),
                }
                for point, previous in pending
            ],
        )
    return counts


async def refresh(
    engine: Callable[[], AsyncEngine],
    app: str,
    build: Callable[[AsyncConnection], Awaitable[list[dict[str, Any]]]],
    every: Every,
    user: UUID,
    client: httpx.AsyncClient | None = None,
) -> dict[str, int] | None:
    if not every.due(user):
        return None
    try:
        shared = await spaces(client) if client is not None else ()
        with as_user(user, shared):
            async with engine().begin() as connection:
                await connection.execute(text(f'set local role "mod_{app}"'))
                return await publish(connection, app, await build(connection))
    except Exception as error:  # noqa: BLE001 - las cifras no paran lo que publica la app
        print(f"cifras · {app}: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return None
