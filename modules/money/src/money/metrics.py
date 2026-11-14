from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_tenancy import current_user
from money import book as books
from money import history, kpis, texts
from money.texts import currency

APP = "money"


def _point(key: str, label: str, day: date, value: Decimal, kind: str = "level") -> dict[str, Any]:
    return contracts.metric(
        APP,
        key=f"{APP}.{key}",
        label=label,
        unit=currency(),
        kind=kind,
        day=day,
        value=float(round(value, 2)),
    )


PENSION = "pension"


def by_day(lo: books.Loaded) -> tuple[dict[date, Decimal], dict[date, Decimal]]:
    book = lo.book
    interest: dict[date, Decimal] = {}
    for fact in book.facts:
        if fact.id not in book.returns or fact.amount <= 0:
            continue
        account = book.accounts.get(fact.account)
        share = account.ownership if account else Decimal(1)
        interest[fact.on] = interest.get(fact.on, Decimal(0)) + fact.amount * share
    pension: dict[date, Decimal] = {}
    for transfer in book.transfers:
        if transfer.out_fact is None:
            continue
        into = book.fact(transfer.in_fact)
        account = book.accounts.get(into.account)
        if account is None or account.type != PENSION or into.amount <= 0:
            continue
        pension[into.on] = pension.get(into.on, Decimal(0)) + into.amount
    return interest, pension


def month_ends(first: date, today: date) -> list[date]:
    out: list[date] = []
    year, month = first.year, first.month
    while (year, month) < (today.year, today.month):
        out.append(kpis.month_end(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return [*out, today]


def today() -> date:
    return texts.today()


async def build(connection: AsyncConnection) -> list[dict[str, Any]]:
    return points(await books.load(connection, current_user.get(None)), today())


def points(lo: books.Loaded, now: date) -> list[dict[str, Any]]:
    years = history.years(lo.flows, lo.valuations) | {now.year}
    found: list[dict[str, Any]] = []
    has_fund = any(one.role == "emergency_fund" for one in lo.book.accounts.values())
    for day in month_ends(date(min(years), 1, 1), now):
        found.append(_point("net_worth", "Net worth", day, kpis.worth(lo, day)[0]))
        found.append(_point("liquid", "Liquid", day, kpis.worth(lo, day, liquid_only=True)[0]))
        found.append(_point("cash", "Cash", day, kpis.cash(lo, day)[0]))
        if has_fund:
            fund = kpis.emergency(lo, day)[0]
            found.append(_point("emergency_fund", "Emergency fund", day, fund))
        if day == now:
            continue
        for key, label, basic in (
            ("month_expense", "Spending of the month", False),
            ("month_basic_expense", "Basic spending of the month", True),
        ):
            spent = kpis.month_expense(lo, day.year, day.month, basic)
            if spent is not None:
                found.append(_point(key, label, day, spent))
    for key, label, basic in (
        ("average_expense", "Monthly spending (average)", False),
        ("average_basic_expense", "Basic spending (average)", True),
    ):
        average, _ = kpis.average_expense(lo, now, basic=basic)
        if average is not None:
            found.append(_point(key, label, now, average))
    interest, pension = by_day(lo)
    found += [
        _point("interest", "Interest received", day, value, "amount")
        for day, value in sorted(interest.items())
        if day <= now
    ]
    found += [
        _point("pension_contribution", "Pension plan contributions", day, value, "amount")
        for day, value in sorted(pension.items())
        if day <= now
    ]
    return found
