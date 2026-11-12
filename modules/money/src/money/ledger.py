from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from itertools import product

from money.model import Account, Book

ZERO = Decimal(0)


def statuses(book: Book) -> dict[str, str]:
    imputed: dict[str, Decimal] = defaultdict(lambda: ZERO)
    basis: dict[str, set[str]] = defaultdict(set)
    for imp in book.imputations:
        imputed[imp.fact] += imp.amount
        basis[imp.fact].add(imp.basis)
    moved = book.transferred()
    out: dict[str, str] = {}
    for f in book.facts:
        if f.source == "inferred":
            continue
        if f.id in book.settlements:
            out[f.id] = "settlement"
        elif f.id in book.returns:
            out[f.id] = "return"
        elif f.id in moved:
            out[f.id] = "transfer"
        elif f.id in book.asking and not basis[f.id]:
            out[f.id] = "ask"
        elif imputed.get(f.id, ZERO) != f.amount:
            out[f.id] = "pending"
        elif "manual" in basis[f.id]:
            out[f.id] = "manual"
        elif "default" in basis[f.id]:
            out[f.id] = "default"
        else:
            out[f.id] = "auto"
    return out


@dataclass(frozen=True)
class BalanceCheck:
    account: str
    ok: bool
    first: date | None
    last: date | None
    gap: Decimal | None


def balance_check(
    book: Book, acc: Account, start: date, end: date, tolerance: Decimal = Decimal("0.01")
) -> BalanceCheck:
    bal = sorted(
        (
            b
            for b in book.balances
            if b.account == acc.id and start - timedelta(days=1) <= b.on <= end
        ),
        key=lambda b: b.on,
    )
    if len(bal) < 2:
        return BalanceCheck(
            acc.id, True, bal[0].on if bal else None, bal[-1].on if bal else None, None
        )
    facts = [f for f in book.facts if f.account == acc.id and f.source != "inferred"]
    if all(b.kind == "closing" for b in bal):
        moved = sum(
            (f.amount for f in facts if bal[0].on < (f.value_on or f.on) <= bal[-1].on), ZERO
        )
        gap = bal[0].amount + moved - bal[-1].amount
        return BalanceCheck(acc.id, abs(gap) <= tolerance, bal[0].on, bal[-1].on, gap)
    worst = None
    for a, b in zip(bal, bal[1:], strict=False):
        sure = sum((f.amount for f in facts if a.on < f.on < b.on), ZERO)
        edge = [f for f in facts if f.on in (a.on, b.on) and a.on != b.on]
        left = _unexplained(edge, a.on, b.amount - a.amount - sure)
        if abs(left) > tolerance:
            worst = -left
    return BalanceCheck(acc.id, worst is None, bal[0].on, bal[-1].on, worst)


def _unexplained(edge, first_day, target) -> Decimal:
    if len(edge) > 14:
        return target
    best = target
    for mask in product((0, 1), repeat=len(edge)):
        total = sum(
            (
                f.amount
                for f, m in zip(edge, mask, strict=True)
                if (m and f.on != first_day) or (not m and f.on == first_day)
            ),
            ZERO,
        )
        if abs(target - total) < abs(best):
            best = target - total
    return best
