from __future__ import annotations

import tomllib
from functools import cache
from pathlib import Path

HERE = Path(__file__).resolve().parent / "catalogs"


@cache
def account_types() -> dict[str, dict]:
    return tomllib.loads((HERE / "account_types.toml").read_text())


@cache
def institutions() -> dict[str, dict]:
    return tomllib.loads((HERE / "institutions.toml").read_text())


def institution(name: str) -> dict:
    known = institutions()
    if name in known:
        return known[name]
    folded = name.strip().lower()
    for key, data in known.items():
        if key.lower() == folded or folded in (a.lower() for a in data.get("aliases", ())):
            return data
    return {}


@cache
def funds() -> dict[str, dict]:
    return tomllib.loads((HERE / "funds.toml").read_text())
