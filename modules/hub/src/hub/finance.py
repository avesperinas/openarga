from __future__ import annotations

import re
import tomllib
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any

MOVEMENT = "finance.movement"
HERE = Path(__file__).resolve().parent / "catalogs"


@cache
def institutions() -> dict[str, dict[str, Any]]:
    return tomllib.loads((HERE / "institutions.toml").read_text())


def fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(plain.casefold().split())


def institution(name: str) -> dict[str, Any]:
    wanted = fold(name or "")
    if not wanted:
        return {}
    for key, data in institutions().items():
        if fold(key) == wanted or wanted in (fold(alias) for alias in data.get("aliases", ())):
            return data
    return {}


def read(known: dict[str, Any], description: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for pattern in known.get("merchant", ()):
        hit = re.search(pattern, description)
        if hit and hit.group(1).strip():
            found["merchant"] = " ".join(hit.group(1).split())
            break
    category = known.get("bank_category")
    hit = re.match(category, description) if category else None
    if hit and hit.group(1).strip():
        found["bank_category"] = hit.group(1).strip()
    internal = known.get("internal")
    if internal and re.search(internal, description, re.IGNORECASE):
        found["own_transfer"] = True
    return found


def enrich(events: list[dict[str, Any]], bank: str) -> list[dict[str, Any]]:
    known = institution(bank)
    if not known:
        return events
    out = []
    for event in events:
        if event.get("type") == MOVEMENT:
            payload = event["payload"]
            extra = read(known, payload.get("description") or "")
            if extra:
                event = {**event, "payload": {**payload, **extra}}
        out.append(event)
    return out
