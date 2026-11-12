from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

TZ = "Europe/Madrid"
MADRID = ZoneInfo(TZ)


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


class Unavailable(RuntimeError):
    pass


def now() -> datetime:
    return datetime.now(MADRID)


def today() -> date:
    return now().date()


def local_day(moment: datetime, tz: str = TZ) -> date:
    return moment.astimezone(ZoneInfo(tz)).date()


def is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


ENQUEUE = text("""
    insert into macros.macros_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :dedup)
""")


async def enqueue(
    connection: AsyncConnection, kind: str, payload: dict[str, Any], dedup: str | None = None
) -> None:
    await connection.execute(
        ENQUEUE,
        {
            "type": f"macros.{kind}",
            "payload": json.dumps(payload, default=str),
            "dedup": dedup or f"{kind}:{uuid.uuid4().hex}",
        },
    )
