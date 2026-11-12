from __future__ import annotations

import json
import unicodedata
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import current_user

TZ = "Europe/Madrid"
MADRID = ZoneInfo(TZ)


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


def now() -> datetime:
    return datetime.now(MADRID)


def today() -> date:
    return now().date()


def me() -> str | None:
    user = current_user.get()
    return str(user) if user else None


def fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


ENQUEUE = text("""
    insert into goals.goals_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :dedup)
""")


async def enqueue(connection: AsyncConnection, kind: str, payload: dict[str, Any]) -> None:
    await connection.execute(
        ENQUEUE,
        {
            "type": f"goals.{kind}",
            "payload": json.dumps(payload, default=str),
            "dedup": f"{kind}:{uuid.uuid4().hex}",
        },
    )
