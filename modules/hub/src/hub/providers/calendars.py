from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

EVENT = "calendar.event"
FEED = "calendar.feed"

LIMIT = 5000


@dataclass(frozen=True)
class Item:
    uid: str
    title: str
    all_day: bool
    start: str
    end: str
    tz: str = "UTC"
    location: str | None = None
    description: str | None = None
    url: str | None = None
    status: str = "confirmed"

    def fingerprint(self) -> str:
        body = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(body.encode()).hexdigest()[:32]


def window(today: date) -> tuple[date, date]:
    return date(today.year - 1, 1, 1), today + timedelta(days=730)


def inside(item: Item, first: date, last: date) -> bool:
    start = date.fromisoformat(item.start[:10])
    end = date.fromisoformat(item.end[:10])
    return start <= last and end >= first


def events(
    connection: Any, provider: str, items: list[Item], now: datetime | None = None
) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    first, last = window(now.date())
    kept: dict[str, Item] = {}
    for item in items:
        if inside(item, first, last):
            kept[item.uid] = item
    if len(kept) > LIMIT:
        raise ValueError(f"la fuente trae {len(kept)} eventos; arga refleja como mucho {LIMIT}")
    out: list[dict[str, Any]] = []
    prints: dict[str, str] = {}
    for item in kept.values():
        fingerprint = item.fingerprint()
        prints[item.uid] = fingerprint
        out.append(
            {
                "ts": now.isoformat(),
                "type": EVENT,
                "payload": {
                    "connection": str(connection.id),
                    **asdict(item),
                    "fingerprint": fingerprint,
                },
                "dedup_hash": f"calendar:{connection.id}:{digest(item.uid)}:{fingerprint}",
            }
        )
    out.append(
        {
            "ts": now.isoformat(),
            "type": FEED,
            "payload": {
                "connection": str(connection.id),
                "provider": provider,
                "label": connection.label,
                "from": first.isoformat(),
                "to": last.isoformat(),
                "events": prints,
            },
            "dedup_hash": f"feed:{connection.id}:{now.isoformat()}",
        }
    )
    return out


def digest(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()[:24]


def clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()) if limit <= 300 else value.strip()
    return cleaned[:limit] or None
