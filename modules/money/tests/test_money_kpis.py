from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from money.book import Loaded, Settings
from money.history import Flow, Valuation
from money.interpret import Interpreter
from money.kpis import compute, month_expense, months_back
from money.model import Account, Balance, Book, Category, Fact, Holding, Imputation
from money.shared import HistoryRow, Income
from money.value import value_at


def acc(id, cls, value, **kw) -> Account:
    return Account(id, id.title(), "Bank", cls, cls, "api", value, **kw)


ACCOUNTS = {
    a.id: a
    for a in [
        acc("main", "cash", "balance", cash=True),
        acc("joint", "cash", "balance", cash=True, ownership=D("0.5"), shared_space=True),
        acc("fund", "investment", "snapshot", ownership=D("0.5"), ibans=("ES00FONDO",)),
        acc("pension", "investment", "snapshot", liquid=False),
        acc("rainy", "cash", "computed", cash=True, role="emergency_fund"),
        acc("house", "real_estate", "manual", liquid=False, ownership=D("0.5")),
    ]
}

CATS = {
    c.id: c
    for c in [
        Category("ocio", "Leisure", "expense", "individual", not_basic=True),
        Category("trabajo", "Work", "expense", "individual", not_living=True),
        Category("salud", "Health", "expense", "individual"),
        Category("super", "Groceries", "expense", "shared", "proportional"),
        Category("viajes", "Travel", "expense", "shared", "proportional", not_basic=True),
    ]
}

TODAY = date(2030, 10, 1)


def loaded(
    facts=(), labels=(), flows=(), valuations=(), history=(), balances=(), holdings=(), prices=None
) -> Loaded:
    book = Interpreter(labels=list(labels)).run(
        Book(
            ACCOUNTS,
            CATS,
            list(facts),
            list(balances),
            holdings=list(holdings),
            prices=prices or {},
        )
    )
    from money.ledger import statuses

    return Loaded(
        settings=Settings(date(2030, 9, 1), "Me", "Another", (), 4, 0, 3),
        book=book,
        statuses=statuses(book),
        merchant_of={},
        unmapped=[],
        entries={},
        incomes=[
            Income("me", date(2030, 1, 1), date(2030, 12, 31), D("30000")),
            Income("other", date(2030, 1, 1), date(2030, 12, 31), D("10000")),
        ],
        history=list(history),
        settled={},
        labels={},
        rules=[],
        flows=list(flows),
        valuations=list(valuations),
    )


def test_a_value_starts_from_the_latest_known_and_moves_by_class():
    facts = [
        Fact("o", "main", date(2030, 9, 20), D("-100"), "a fondo", counterparty_iban="ES00FONDO"),
        Fact("x", "main", date(2030, 9, 25), D("-50"), "compra"),
    ]
    lo = loaded(
        facts,
        balances=[Balance("main", date(2030, 9, 10), D("1000"))],
        valuations=[Valuation("fund", date(2030, 9, 1), D("5000"))],
    )
    assert value_at(lo.book, ACCOUNTS["main"], TODAY, lo.valuations).amount == D("850")
    fund = value_at(lo.book, ACCOUNTS["fund"], TODAY, lo.valuations)
    assert fund.amount == D("5100") and fund.since == date(2030, 9, 1)
    assert not value_at(lo.book, ACCOUNTS["house"], TODAY, lo.valuations).known


def test_networth_liquid_cash_and_fund_by_what_each_account_is():
    v = [
        Valuation("main", date(2030, 9, 30), D("1000")),
        Valuation("joint", date(2030, 9, 30), D("400")),
        Valuation("fund", date(2030, 9, 30), D("6000")),
        Valuation("pension", date(2030, 9, 30), D("2000")),
        Valuation("rainy", date(2030, 9, 30), D("900")),
        Valuation("house", date(2030, 9, 30), D("90000")),
        Valuation("main", date(2029, 9, 30), D("500")),
    ]
    k = {x.key: x for x in compute(loaded(valuations=v), TODAY)}
    assert k["networth"].value == D("1000") + D("200") + D("3000") + D("2000") + D("900")
    assert k["networth"].previous == D("500")
    assert k["liquid"].value == k["networth"].value - D("2000")
    assert k["cash"].value == D("1400")
    assert k["emergency"].value == D("900")


def test_monthly_expense_counts_my_share_and_leaves_out_what_is_not_living():
    history = [HistoryRow(2030, 3, "expense", D("300"), "Groceries", "proportional", "account")]
    flows = [
        Flow(2030, 3, "expense", D("100"), "Leisure"),
        Flow(2030, 3, "expense", D("400"), "Work"),
        Flow(2030, 3, "expense", D("50"), "Health"),
    ]
    lo = loaded(flows=flows, history=history)
    assert month_expense(lo, 2030, 3, basic=False) == D("150") + D("225")
    assert month_expense(lo, 2030, 3, basic=True) == D("50") + D("225")
    assert month_expense(lo, 2030, 2, basic=False) is None


def test_after_the_cutoff_the_book_counts_and_a_refund_subtracts():
    facts = [
        Fact("a", "main", date(2030, 9, 5), D("-80"), "cine"),
        Fact("b", "main", date(2030, 9, 6), D("20"), "bizum cine"),
        Fact("c", "joint", date(2030, 9, 7), D("-100"), "super"),
    ]
    labels = [
        __import__("money.interpret", fromlist=["Label"]).Label(
            "a", (Imputation("a", D("-80"), "expense", "individual", "ocio"),)
        ),
        __import__("money.interpret", fromlist=["Label"]).Label(
            "b", (Imputation("b", D("20"), "expense", "individual", "ocio"),)
        ),
        __import__("money.interpret", fromlist=["Label"]).Label(
            "c", (Imputation("c", D("-100"), "expense", "shared", "super", "account"),)
        ),
    ]
    lo = loaded(facts, labels)
    assert month_expense(lo, 2030, 9, basic=False) == D("60") + D("75")
    assert month_expense(lo, 2030, 9, basic=True) == D("75")


def test_the_average_is_of_the_months_there_are_and_compares_only_with_a_base():
    flows = [Flow(2030, m, "expense", D("100"), "Health") for m in (6, 7, 8)]
    k = {x.key: x for x in compute(loaded(flows=flows), TODAY)}
    assert k["expense"].value == D("75") and k["expense"].detail == "Average of 4 months"
    assert k["expense"].previous is None
    assert k["emergency"].target == D("225")
    assert months_back(TODAY, 2) == [(2030, 9), (2030, 8)]


SHOT = date(2030, 9, 26)
PRICES = {
    "FUND": [
        (date(2030, 9, 24), D("100")),
        (date(2030, 9, 25), D("110")),
        (date(2030, 9, 29), D("120")),
    ],
    "ETF": [(date(2030, 9, 26), D("50")), (date(2030, 9, 29), D("45"))],
}


def portfolio(**kw) -> Loaded:
    return loaded(
        balances=[Balance("pension", SHOT, D("1000"))],
        holdings=[
            Holding("pension", SHOT, "FUND", D("600"), price=D("100")),
            Holding("pension", SHOT, "ETF", D("300")),
            Holding("pension", SHOT, "EUR", D("100"), price=D("1")),
        ],
        prices=PRICES,
        **kw,
    )


def test_between_photos_each_fund_moves_with_its_price():
    lo = portfolio()
    v = value_at(lo.book, ACCOUNTS["pension"], date(2030, 9, 30), lo.valuations)
    assert v.amount == D("1000") + D("600") * D("0.2") - D("300") * D("0.1")
    assert v.since == SHOT and v.estimated == date(2030, 9, 29)
    same = value_at(lo.book, ACCOUNTS["pension"], SHOT, lo.valuations)
    assert same.amount == D("1000") and same.estimated is None


def test_a_later_value_without_photo_moves_with_the_last_photo_weights():
    lo = portfolio(valuations=[Valuation("pension", date(2030, 9, 28), D("2000"))])
    v = value_at(lo.book, ACCOUNTS["pension"], date(2030, 9, 30), lo.valuations)
    expected = D("2000") * (
        D("0.6") * (D("120") / D("110") - 1) + D("0.3") * (D("45") / D("50") - 1)
    )
    assert v.amount == (D("2000") + expected).quantize(D("0.01"))


def test_the_summary_says_which_values_are_estimated():
    k = {x.key: x for x in compute(portfolio(), date(2030, 9, 30))}
    assert "Pension estimated at 29/9" in k["networth"].carried
