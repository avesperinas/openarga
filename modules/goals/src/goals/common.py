from __future__ import annotations

import json
import unicodedata
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module import i18n, preferences
from arga_tenancy import current_user

CATALOGS = Path(__file__).parent / "i18n"


def t(key: str, **values: object) -> str:
    return i18n.t(CATALOGS, key, preferences.current().locale, **values)


def zone() -> ZoneInfo:
    return preferences.current().zone


def zone_name() -> str:
    return preferences.current().timezone


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


def now() -> datetime:
    return datetime.now(zone())


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


def number(value: float, decimals: int) -> str:
    grouped = f"{value:,.{decimals}f}"
    return (
        grouped.replace(",", "\0")
        .replace(".", t("number.decimal"))
        .replace("\0", t("number.group"))
    )


def plural(key: str, count: int, **values: object) -> str:
    return t(f"{key}_one", **values) if count == 1 else t(f"{key}_many", count=count, **values)
