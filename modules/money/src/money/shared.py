from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from money.model import Book

ZERO = Decimal(0)
HALF = Decimal("0.5")


@dataclass(frozen=True)
class Income:
    person: str
    from_on: date
    to_on: date
    salary: Decimal
    extra: Decimal = ZERO


def totals(
    incomes: list[Income], year: int, fixed: Mapping[str, Decimal] | None = None
) -> dict[str, Decimal]:
    first, last = date(year, 1, 1), date(year, 12, 31)
    days_year = 366 if calendar.isleap(year) else 365
    fixed = fixed or {}
    total = {"me": fixed.get("me", ZERO), "other": fixed.get("other", ZERO)}
    for inc in incomes:
        if inc.person in fixed:
            continue
        days = (min(inc.to_on, last) - max(inc.from_on, first)).days + 1
        if days <= 0:
            continue
        daily = inc.salary / days_year + inc.extra / days
        total[inc.person] = total.get(inc.person, ZERO) + daily * days
    return total


def ratio(incomes: list[Income], year: int, fixed: Mapping[str, Decimal] | None = None) -> Decimal:
    total = totals(incomes, year, fixed)
    both = total["me"] + total["other"]
    return total["me"] / both if both else HALF


@dataclass
class Month:
    year: int
    month: int
    source: str
    by_category: dict[str, Decimal] = field(default_factory=dict)
    split_of: dict[str, str] = field(default_factory=dict)
    paid_me: Decimal = ZERO
    paid_other: Decimal = ZERO
    paid_account: Decimal = ZERO
    deposits_me: Decimal = ZERO
    deposits_other: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return sum(self.by_category.values(), ZERO)

    def obligation_me(self, r: Decimal) -> Decimal:
        return sum(
            (
                a * (HALF if self.split_of.get(c) == "fifty_fifty" else r)
                for c, a in self.by_category.items()
            ),
            ZERO,
        )

    def balance_me(self, r: Decimal) -> Decimal:
        ob_me = self.obligation_me(r)
        ob_other = self.total - ob_me
        raw_me = self.deposits_me + self.paid_me - ob_me
        raw_other = self.deposits_other + self.paid_other - ob_other
        return (raw_me - raw_other) / 2


@dataclass(frozen=True)
class HistoryRow:
    year: int
    month: int
    kind: str
    amount: Decimal
    category: str | None = None
    split: str | None = None
    payer: str | None = None


def from_history(rows: list[HistoryRow], year: int, month: int) -> Month:
    m = Month(year, month, "history")
    for r in rows:
        if (r.year, r.month) != (year, month):
            continue
        if r.kind == "deposit":
            if r.payer == "me":
                m.deposits_me += r.amount
            else:
                m.deposits_other += r.amount
            continue
        name = r.category or "Otros"
        m.by_category[name] = m.by_category.get(name, ZERO) + r.amount
        if r.split:
            m.split_of[name] = r.split
        if r.payer == "me":
            m.paid_me += r.amount
        elif r.payer == "other":
            m.paid_other += r.amount
        else:
            m.paid_account += r.amount
    return m


def from_book(book: Book, year: int, month: int) -> Month:
    m = Month(year, month, "book")
    for imp in book.imputations:
        if imp.nature != "expense" or imp.ownership != "shared":
            continue
        fact = book.fact(imp.fact)
        if (fact.on.year, fact.on.month) != (year, month):
            continue
        cat = book.categories[imp.category]
        spent = -imp.amount
        m.by_category[cat.name] = m.by_category.get(cat.name, ZERO) + spent
        if cat.split:
            m.split_of[cat.name] = cat.split
        if imp.payer == "me":
            m.paid_me += spent
        elif imp.payer == "other":
            m.paid_other += spent
        else:
            m.paid_account += spent
    for t in book.transfers:
        inn = book.fact(t.in_fact)
        acc = book.accounts.get(inn.account)
        if not (acc and acc.shared_space):
            continue
        when = book.fact(t.out_fact).on if t.out_fact else inn.on
        if (when.year, when.month) != (year, month):
            continue
        if t.out_fact is None:
            m.deposits_other += inn.amount
        else:
            src = book.accounts.get(book.fact(t.out_fact).account)
            if src and not src.shared_space:
                m.deposits_me += inn.amount
    return m


def year_months(
    book: Book, history: list[HistoryRow], year: int, cutoff: date | None, today: date
) -> list[Month]:
    out = []
    for month in range(1, 13):
        if date(year, month, 1) > today:
            break
        if cutoff and date(year, month, 1) < cutoff:
            out.append(from_history(history, year, month))
        else:
            out.append(from_book(book, year, month))
    return out


@dataclass(frozen=True)
class YearBalance:
    year: int
    ratio_me: Decimal
    balance_me: Decimal
    total: Decimal
    months: list[Month]
    by_category: dict[str, Decimal]


def year_balance(months: list[Month], r: Decimal, year: int) -> YearBalance:
    by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for m in months:
        for c, a in m.by_category.items():
            by_cat[c] += a
    return YearBalance(
        year=year,
        ratio_me=r,
        balance_me=sum((m.balance_me(r) for m in months), ZERO),
        total=sum((m.total for m in months), ZERO),
        months=months,
        by_category=dict(by_cat),
    )


def monthly_average(months: list[Month], year: int, today: date) -> tuple[int, dict[str, Decimal]]:
    closed = [m for m in months if (year, m.month) < (today.year, today.month)]
    by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for m in closed:
        for c, a in m.by_category.items():
            by_cat[c] += a
    return len(closed), {c: a / len(closed) for c, a in by_cat.items()}
