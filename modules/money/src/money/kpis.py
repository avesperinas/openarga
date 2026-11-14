from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from money import history
from money.book import Loaded, ratio_of
from money.model import Account
from money.shared import from_book, from_history
from money.texts import t
from money.value import value_at

ZERO = Decimal(0)
MIN_MONTHS_TO_COMPARE = 6


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    value: Decimal | None
    previous: Decimal | None = None
    target: Decimal | None = None
    detail: str | None = None
    carried: list[str] = field(default_factory=list)
    """The accounts whose value comes from before today (the last valuation), with its date."""


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def months_back(today: date, count: int, offset: int = 0) -> list[tuple[int, int]]:
    out = []
    y, m = today.year, today.month
    for _ in range(offset + count):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append((y, m))
    return out[offset:]


def _sum(lo: Loaded, on: date, keep) -> tuple[Decimal, list[str]]:
    total, carried = ZERO, []
    for account in lo.book.accounts.values():
        if not keep(account):
            continue
        v = value_at(lo.book, account, on, lo.valuations)
        total += v.amount * (Decimal(1) if keep(account) == "whole" else account.ownership)
        if v.estimated:
            carried.append(
                f"{account.name} "
                + t("widget.estimated", day=f"{v.estimated.day}/{v.estimated.month}")
            )
        elif v.since and (on - v.since).days > 7 and account.asset_class != "real_estate":
            carried.append(
                f"{account.name} " + t("widget.as_of", day=f"{v.since.day}/{v.since.month}")
            )
    return total, carried


def worth(lo: Loaded, on: date, liquid_only: bool = False) -> tuple[Decimal, list[str]]:
    def keep(a: Account):
        return a.asset_class != "real_estate" and (a.liquid or not liquid_only)

    return _sum(lo, on, keep)


def cash(lo: Loaded, on: date) -> tuple[Decimal, list[str]]:
    def keep(a: Account):
        return "whole" if a.cash and a.role != "emergency_fund" else False

    return _sum(lo, on, keep)


def emergency(lo: Loaded, on: date) -> tuple[Decimal, list[str], bool]:
    total, carried = _sum(lo, on, lambda a: a.role == "emergency_fund")
    return total, carried, any(a.role == "emergency_fund" for a in lo.book.accounts.values())


def month_expense(lo: Loaded, year: int, month: int, basic: bool) -> Decimal | None:
    cats = lo.book.categories.values()
    flags = {
        (c.ownership, c.name): (c.not_living, c.not_basic) for c in cats if c.nature == "expense"
    }

    def counts(ownership: str, name: str) -> bool:
        not_living, not_basic = flags.get((ownership, name), (False, False))
        return not not_living and not (basic and not_basic)

    cutoff = lo.settings.cutoff
    before = cutoff is not None and date(year, month, 1) < cutoff
    r = ratio_of(lo, year)
    if before:
        hm = history.month(lo.flows, year, month)
        if not hm.expense:
            return None
        personal = sum((a for n, a in hm.expense.items() if counts("individual", n)), ZERO)
        shared_month = from_history(lo.history, year, month)
    else:
        if cutoff is None and not any(
            (f.on.year, f.on.month) == (year, month) for f in lo.book.facts
        ):
            return None
        personal = ZERO
        for imp in lo.book.imputations:
            if imp.nature != "expense" or imp.ownership != "individual":
                continue
            f = lo.book.fact(imp.fact)
            if (f.on.year, f.on.month) != (year, month):
                continue
            if counts("individual", lo.book.categories[imp.category].name):
                personal -= imp.amount
        shared_month = from_book(lo.book, year, month)
    shared = ZERO
    for name, amount in shared_month.by_category.items():
        if not counts("shared", name):
            continue
        share = Decimal("0.5") if shared_month.split_of.get(name) == "fifty_fifty" else r
        shared += amount * share
    return personal + shared


def average_expense(
    lo: Loaded, today: date, basic: bool, offset: int = 0
) -> tuple[Decimal | None, int]:
    values = [
        v
        for y, m in months_back(today, 12, offset)
        if (v := month_expense(lo, y, m, basic)) is not None
    ]
    if not values:
        return None, 0
    return sum(values, ZERO) / len(values), len(values)


def compute(lo: Loaded, today: date) -> list[Kpi]:
    year_ago = today - timedelta(days=365)

    now_worth, carried = worth(lo, today)
    then_worth, _ = worth(lo, year_ago)
    now_liquid, carried_liquid = worth(lo, today, liquid_only=True)
    then_liquid, _ = worth(lo, year_ago, liquid_only=True)
    now_cash, carried_cash = cash(lo, today)
    fund, carried_fund, has_fund = emergency(lo, today)

    out = [
        Kpi("networth", t("kpi.networth"), now_worth, then_worth, carried=carried),
        Kpi("liquid", t("kpi.liquid"), now_liquid, then_liquid, carried=carried_liquid),
        Kpi("cash", t("kpi.cash"), now_cash, carried=carried_cash),
    ]

    expense, months = average_expense(lo, today, basic=False)
    expense_before, months_before = average_expense(lo, today, basic=False, offset=12)
    basic, _ = average_expense(lo, today, basic=True)
    basic_before, _ = average_expense(lo, today, basic=True, offset=12)
    comparable = months_before >= MIN_MONTHS_TO_COMPARE

    target = basic * lo.settings.emergency_months if basic is not None else None
    out.append(
        Kpi(
            "emergency",
            t("kpi.emergency"),
            fund if has_fund else None,
            target=target,
            detail=(None if has_fund else t("kpi.no_emergency")),
            carried=carried_fund,
        )
    )
    detail = t("kpi.average_of", months=months) if months and months < 12 else None
    out.append(
        Kpi(
            "expense",
            t("kpi.expense"),
            expense,
            expense_before if comparable else None,
            detail=detail,
        )
    )
    out.append(
        Kpi("basic", t("kpi.basic"), basic, basic_before if comparable else None, detail=detail)
    )
    return out
