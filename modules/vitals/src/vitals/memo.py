from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Hashable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import current_user

MARGIN = timedelta(minutes=1)
FULL_EVERY = 6 * 3600.0
NEVER = datetime(1970, 1, 1, tzinfo=UTC)
SIZE = 512
_KEPT: OrderedDict[tuple, Any] = OrderedDict()


def _key(name: str, extra: Hashable) -> tuple:
    return (name, current_user.get(), extra)


def get(name: str, extra: Hashable = None) -> Any | None:
    key = _key(name, extra)
    if key not in _KEPT:
        return None
    _KEPT.move_to_end(key)
    return _KEPT[key]


def put(name: str, extra: Hashable, value: Any, keep: int | None = None) -> None:
    key = _key(name, extra)
    _KEPT[key] = value
    _KEPT.move_to_end(key)
    if keep is not None:
        same = [one for one in _KEPT if one[:2] == key[:2]]
        for one in same[: max(0, len(same) - keep)]:
            del _KEPT[one]
    while len(_KEPT) > SIZE:
        _KEPT.popitem(last=False)


@dataclass
class Read:
    read_at: float = field(default_factory=time.monotonic, kw_only=True)

    def expired(self) -> bool:
        return time.monotonic() - self.read_at > FULL_EVERY


def after(last: datetime | None) -> datetime:
    return NEVER if last is None else last - MARGIN


def latest(*moments: datetime | None) -> datetime | None:
    known = [one for one in moments if one is not None]
    return max(known) if known else None


def _last_arrival(types: tuple[str, ...]):
    columns = ", ".join(
        f"(select max(ingested_at) from vitals.events where type = '{kind}')" for kind in types
    )
    return text(f"select greatest({columns})")


async def last_arrival(connection: AsyncConnection, types: tuple[str, ...]) -> datetime | None:
    return await connection.scalar(_last_arrival(types))


def forget() -> None:
    _KEPT.clear()
