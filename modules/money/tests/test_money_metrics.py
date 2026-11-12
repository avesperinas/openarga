from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from test_money_kpis import TODAY, loaded

import arga_contracts as contracts
from money.history import Valuation
from money.kpis import compute
from money.metrics import month_ends, points


def test_one_point_per_closed_month_and_one_today() -> None:
    assert month_ends(date(2030, 8, 1), TODAY) == [date(2030, 8, 31), date(2030, 9, 30), TODAY]


def test_the_figures_are_the_kpis_of_the_app() -> None:
    lo = loaded(
        valuations=[
            Valuation("main", date(2030, 9, 30), D("1000")),
            Valuation("fund", date(2030, 9, 30), D("6000")),
            Valuation("pension", date(2030, 9, 30), D("2000")),
            Valuation("rainy", date(2030, 9, 30), D("900")),
        ]
    )
    found = {contracts.metric_identity(one): one for one in points(lo, TODAY)}
    for one in found.values():
        assert one == contracts.metric("money", **one)
    kpis = {k.key: float(k.value) for k in compute(lo, TODAY) if k.value is not None}
    today = TODAY.isoformat()
    assert found[f"money.net_worth@{today}"]["value"] == kpis["networth"]
    assert found[f"money.liquid@{today}"]["value"] == kpis["liquid"]
    assert found[f"money.cash@{today}"]["value"] == kpis["cash"]
    assert found[f"money.emergency_fund@{today}"]["value"] == kpis["emergency"]
    assert found["money.net_worth@2030-09-30"]["label"] == "Patrimonio"


def test_interest_and_pension_contributions_are_published_day_by_day() -> None:
    from test_money_kpis import ACCOUNTS, CATS, acc

    from money.metrics import by_day
    from money.model import Book, Fact, Transfer

    accounts = {
        **ACCOUNTS,
        "joint": acc("joint", "savings", "balance", ownership=D("0.5")),
        "plan": acc("plan", "pension", "snapshot", liquid=False),
    }
    facts = [
        Fact("i1", "joint", date(2030, 6, 30), D("40"), "intereses"),
        Fact("o1", "main", date(2030, 7, 1), D("-100"), "aportación"),
        Fact("p1", "plan", date(2030, 7, 1), D("100"), "aportación"),
        Fact("p2", "plan", date(2030, 7, 2), D("50"), "aportación de la empresa"),
    ]
    book = Book(
        accounts,
        CATS,
        facts,
        transfers=[Transfer("o1", "p1"), Transfer(None, "p2")],
        returns={"i1"},
    )
    lo = loaded()
    lo.book = book

    interest, pension = by_day(lo)
    found = {contracts.metric_identity(one): one for one in points(lo, TODAY)}

    assert interest == {date(2030, 6, 30): D("20.0")}
    assert pension == {date(2030, 7, 1): D("100")}
    assert found["money.interest@2030-06-30"]["kind"] == "amount"
    assert found["money.interest@2030-06-30"]["value"] == 20.0
    assert found["money.pension_contribution@2030-07-01"]["value"] == 100.0
