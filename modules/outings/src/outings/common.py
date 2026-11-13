from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import notify
from arga_module import preferences


def zone() -> ZoneInfo:
    person = preferences.current()
    return person.zone if person != preferences.defaults() else notify.zone()


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    def __init__(self, message: str, code: str = "INVALID") -> None:
        super().__init__(message)
        self.code = code


def now() -> datetime:
    return datetime.now(zone())


def today() -> date:
    return now().date()


ENQUEUE = text("""
    insert into outings.outings_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :hash)
    on conflict (user_id, dedup_hash) do nothing
""")


async def enqueue(
    connection: AsyncConnection, kind: str, key: str, payload: dict[str, Any]
) -> None:
    said = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(said.encode()).hexdigest()[:16]
    await connection.execute(ENQUEUE, {"type": kind, "payload": said, "hash": f"{key}:{digest}"})
