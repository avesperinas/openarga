from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from hub.finance import fold

HERE = Path(__file__).resolve().parent / "catalogs"
CASH = "EUR"
CASH_NAMES = {"liquidez", "efectivo", "cash"}


@dataclass(frozen=True)
class Fund:
    name: str
    symbol: str
    currency: str
    isin: str | None = None


@cache
def catalogue() -> tuple[Fund, ...]:
    found = tomllib.loads((HERE / "funds.toml").read_text())
    return tuple(
        Fund(name, data["symbol"], data["currency"], data.get("isin"))
        for name, data in found.items()
    )


SAME_WORD = {"idx": "index", "gbl": "global", "government": "gov", "govt": "gov"}
NOISE = {"fund", "the", "etf", "acc", "eur", "accumulating", "class", "shares", "inst", "plus"}
NOISE |= {"h", "hedged"}


def canonical(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", fold(name))
    return " ".join(SAME_WORD.get(word, word) for word in words if word not in NOISE)


def symbol_of(name: str) -> str | None:
    wanted = canonical(name)
    if wanted in CASH_NAMES:
        return CASH
    return next(
        (fund.symbol for fund in catalogue() if canonical(fund.name) == wanted),
        None,
    )
