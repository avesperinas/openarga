from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from arga_contracts import RECORD, BadContract, record
from arga_tenancy import as_user, kernel_url, user_headers

APP = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
EVERY_SECONDS = float(os.environ.get("RECORDS_EVERY_SECONDS", "120"))


def _outbox(app: str) -> str:
    if not APP.fullmatch(app):
        raise ValueError(f"'{app}' is not an app id")
    return f'"{app}"."{app}_outbox"'


def last_published(app: str) -> str:
    return (
        f"select distinct on (key) id as row_id, payload->'{RECORD}' as item "
        f"from {_outbox(app)} where type = :type and key like 'record:%' "
        "order by key, id desc"
    )


OUTBOX_KEY = (
    "case"
    " when payload ? 'record' then 'record:' || (payload->'record'->>'id')"
    " when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key')"
    " || '@' || (payload->'metric'->>'day')"
    " when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')"
    " end"
)


PRUNE_AFTER_DAYS = 7
PRUNE_BATCH = 500


def prune_superseded(app: str) -> str:
    outbox = _outbox(app)
    return (
        f"delete from {outbox} where id in ("
        f"  select old.id from {outbox} old"
        "   where old.key is not null and old.published_at is not null"
        f"    and old.published_at < now() - make_interval(days => {PRUNE_AFTER_DAYS})"
        f"    and exists (select 1 from {outbox} newer where newer.user_id = old.user_id"
        "     and newer.type = old.type and newer.key = old.key and newer.id > old.id)"
        f"  limit {PRUNE_BATCH})"
    )


def _dedup(item: dict[str, Any], previous: int) -> str:
    said = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "record:" + hashlib.sha256(f"{item['id']}\n{previous}\n{said}".encode()).hexdigest()


async def publish(
    connection: AsyncConnection, app: str, records: list[dict[str, Any]]
) -> dict[str, int]:
    type_ = f"{app}.{RECORD}"
    now: dict[str, dict[str, Any]] = {}
    for one in records:
        if one["id"] in now:
            raise BadContract(f"Record does not match: repeated id: {one['id']}")
        now[one["id"]] = one
    published = {
        row.item["id"]: (row.row_id, row.item)
        for row in (await connection.execute(text(last_published(app)), {"type": type_})).all()
    }
    pending: list[tuple[dict[str, Any], int]] = []
    counts = {"added": 0, "changed": 0, "removed": 0}
    for id_, item in now.items():
        before = published.get(id_)
        if before is not None and before[1] == item:
            continue
        counts["added" if before is None or before[1].get("removed") else "changed"] += 1
        pending.append((item, before[0] if before else 0))
    for id_, (row_id, item) in published.items():
        if id_ in now or item.get("removed"):
            continue
        gone = record(**{**item, "removed": True, "body": "", "properties": {}})
        pending.append((gone, row_id))
        counts["removed"] += 1
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
                    "payload": json.dumps({RECORD: item}, ensure_ascii=False),
                    "dedup": _dedup(item, previous),
                }
                for item, previous in pending
            ],
        )
    await prune(connection, app)
    return counts


async def prune(connection: AsyncConnection, app: str) -> int:
    try:
        async with connection.begin_nested():
            result = await connection.execute(text(prune_superseded(app)))
    except Exception as error:  # noqa: BLE001 - pruning must not stop publishing
        print(f"prune · {app}: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 0
    return result.rowcount or 0


class Every:
    def __init__(self, seconds: float = EVERY_SECONDS) -> None:
        self.seconds = seconds
        self._last: dict[Any, float] = {}

    def due(self, key: Any) -> bool:
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and now - last < self.seconds:
            return False
        self._last[key] = now
        return True

    def forget(self, key: Any) -> None:
        self._last.pop(key, None)


class Never(Every):
    def due(self, key: Any) -> bool:  # noqa: ARG002
        return False


async def spaces(client: httpx.AsyncClient) -> tuple[UUID, ...]:
    try:
        response = await client.get(
            f"{kernel_url()}/internal/spaces", headers=user_headers(), timeout=10.0
        )
        response.raise_for_status()
        return tuple(UUID(one["id"]) for one in response.json())
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return ()


async def refresh(
    client: httpx.AsyncClient,
    engine: Callable[[], AsyncEngine],
    app: str,
    build: Callable[[AsyncConnection], Awaitable[list[dict[str, Any]]]],
    every: Every,
    user: UUID,
) -> dict[str, int] | None:
    if not every.due(user):
        return None
    try:
        with as_user(user, await spaces(client)):
            async with engine().begin() as connection:
                await connection.execute(text(f'set local role "mod_{app}"'))
                return await publish(connection, app, await build(connection))
    except Exception as error:  # noqa: BLE001 - records must not stop what the app publishes
        print(f"records · {app}: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return None


MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def number(value: float | int, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}"


def trimmed(value: float | int, decimals: int = 2) -> str:
    shown = number(value, decimals)
    if "." in shown:
        shown = shown.rstrip("0").rstrip(".")
    return shown


def euros(value: float | int) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}€{number(abs(value), 2)}"


def long_date(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def month_name(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def weekday(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def link(app: str, id_: str, shown: str) -> str:
    clean = shown.replace("|", "-").replace("[", "(").replace("]", ")").replace("\n", " ")
    return f"[[{app}:{id_}|{clean}]]"


def property_name(label: str) -> str:
    folded = unicodedata.normalize("NFKD", label.casefold())
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    name = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")[:40].rstrip("_") or "campo"
    if not name[0].isalpha():
        name = f"c_{name}"[:40]
    return f"{name}_" if name in ("arga", "tipo") else name


def cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    lines = ["| " + " | ".join(cell(h) for h in headers) + " |"]
    lines.append("|" + "|".join(" --- " for _ in headers) + "|")
    lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def sections(*parts: str | None) -> str:
    return "\n\n".join(part.strip("\n") for part in parts if part and part.strip())


__all__ = [
    "EVERY_SECONDS",
    "Every",
    "Never",
    "cell",
    "euros",
    "last_published",
    "link",
    "long_date",
    "month_name",
    "number",
    "property_name",
    "publish",
    "refresh",
    "sections",
    "spaces",
    "table",
    "trimmed",
    "weekday",
]
