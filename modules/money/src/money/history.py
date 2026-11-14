from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from money.texts import t

ZERO = Decimal(0)


@dataclass(frozen=True)
class Flow:
    year: int
    month: int
    kind: str
    amount: Decimal
    category: str | None = None
    account: str | None = None
    mine: bool = True


@dataclass(frozen=True)
class Valuation:
    account: str
    on: date
    value: Decimal
    source: str = "history"


@dataclass
class Month:
    year: int
    month: int
    income: dict[str, Decimal] = field(default_factory=dict)
    expense: dict[str, Decimal] = field(default_factory=dict)
    contributions: dict[str, Decimal] = field(default_factory=dict)
    """Yours, by account."""
    others: dict[str, Decimal] = field(default_factory=dict)
    """Another member's, by account."""


def month(flows: list[Flow], year: int, m: int) -> Month:
    out = Month(year, m)
    for f in flows:
        if (f.year, f.month) != (year, m):
            continue
        if f.kind == "contribution":
            bucket = out.contributions if f.mine else out.others
            bucket[f.account or "?"] = bucket.get(f.account or "?", ZERO) + f.amount
        else:
            bucket = out.income if f.kind == "income" else out.expense
            name = f.category or t("category.none")
            bucket[name] = bucket.get(name, ZERO) + f.amount
    return out


def years(flows: list[Flow], valuations: list[Valuation]) -> set[int]:
    return {f.year for f in flows} | {v.on.year for v in valuations}


def latest(valuations: list[Valuation], on: date) -> dict[str, Valuation]:
    out: dict[str, Valuation] = {}
    for v in sorted(valuations, key=lambda v: v.on):
        if v.on <= on:
            out[v.account] = v
    return out


def by_account(valuations: list[Valuation]) -> dict[str, list[Valuation]]:
    out: dict[str, list[Valuation]] = defaultdict(list)
    for v in sorted(valuations, key=lambda v: v.on):
        out[v.account].append(v)
    return dict(out)
