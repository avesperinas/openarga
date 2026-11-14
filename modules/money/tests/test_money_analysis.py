from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest

from money import analysis
from money.book import Loaded, Settings
from money.history import Flow, Valuation
from money.interpret import Interpreter, Label
from money.kpis import compute
from money.ledger import statuses
from money.model import OTHER, Account, Book, Category, Fact, Imputation
from money.shared import HistoryRow, Income


def acc(id, cls, value, type=None, **kw) -> Account:
    return Account(id, id.title(), "Bank", type or cls, cls, "api", value, **kw)


ACCOUNTS = {
    a.id: a
    for a in [
        acc("main", "cash", "balance", "current", cash=True),
        acc(
            "joint", "cash", "balance", "current", cash=True, ownership=D("0.5"), shared_space=True
        ),
        acc("fund", "investment", "snapshot", "fund", ownership=D("0.5"), ibans=("ES00FONDO",)),
        acc("house", "real_estate", "manual", "real_estate", liquid=False, ownership=D("0.5")),
    ]
}

CATS = {
    c.id: c
    for c in [
        Category("salario", "Salary", "income", "individual"),
        Category("otros", "Other income", "income", "individual"),
        Category("ocio", "Leisure", "expense", "individual", not_basic=True),
        Category("salud", "Health", "expense", "individual"),
        Category("super", "Groceries", "expense", "shared", "proportional"),
        Category("alquiler", "Rent", "expense", "shared", "fifty_fifty"),
    ]
}

CUTOFF = date(2030, 9, 1)
TODAY = date(2030, 11, 10)


def label(
    fact: str, amount: str, category: str, nature: str, ownership: str, payer=None, equity_in=None
) -> Label:
    return Label(
        fact,
        (Imputation(fact, D(amount), nature, ownership, category, payer, equity_in, "manual"),),
    )


def loaded(facts=(), labels=(), flows=(), valuations=(), history=()) -> Loaded:
    book = Interpreter(labels=list(labels)).run(Book(ACCOUNTS, CATS, list(facts), []))
    return Loaded(
        settings=Settings(CUTOFF, "Me", "Another", (), 4, 0, 3),
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


def book_with_payrolls() -> Loaded:
    facts = [
        Fact("n1", "main", date(2030, 9, 28), D("2000"), "nomina"),
        Fact("adj", "main", date(2030, 10, 2), D("5"), "nomina ajuste"),
        Fact("n2", "main", date(2030, 10, 29), D("2000"), "nomina"),
        Fact("cine", "main", date(2030, 10, 5), D("-60"), "cine"),
        Fact("super", "joint", date(2030, 10, 6), D("-200"), "super"),
        Fact(
            "fondo", "main", date(2030, 10, 7), D("-300"), "a fondo", counterparty_iban="ES00FONDO"
        ),
        Fact("casa", "main", date(2030, 10, 8), D("-1000"), "virgen"),
        Fact("x", "main", date(2030, 9, 3), D("-40"), "nothing in it"),
    ]
    labels = [
        label("n1", "2000", "salario", "income", "individual"),
        label("adj", "5", "salario", "income", "individual"),
        label("n2", "2000", "salario", "income", "individual"),
        label("cine", "-60", "ocio", "expense", "individual"),
        label("super", "-200", "super", "expense", "shared", "account"),
        label("casa", "-1000", "alquiler", "expense", "shared", "me", "house"),
    ]
    flows = [
        Flow(2030, 8, "income", D("2000"), "Salary"),
        Flow(2030, 8, "expense", D("100"), "Health"),
        Flow(2030, 8, "contribution", D("200"), account="fund"),
        Flow(2030, 8, "contribution", D("200"), account="fund", mine=False),
    ]
    history = [HistoryRow(2030, 8, "expense", D("400"), "Groceries", "proportional", "account")]
    valuations = [
        Valuation("main", date(2030, 8, 31), D("1000")),
        Valuation("joint", date(2030, 8, 31), D("600")),
        Valuation("fund", date(2030, 8, 31), D("420")),
        Valuation("fund", date(2030, 10, 31), D("1000")),
        Valuation("house", date(2030, 8, 31), D("50000")),
    ]
    return loaded(facts, labels, flows, valuations, history)


def test_the_previous_period_has_the_same_shape():
    assert analysis.previous_period(date(2030, 3, 1), date(2030, 3, 31)) == (
        date(2030, 2, 1),
        date(2030, 2, 28),
    )
    assert analysis.previous_period(date(2030, 1, 1), date(2030, 3, 31)) == (
        date(2029, 10, 1),
        date(2029, 12, 31),
    )
    assert analysis.previous_period(date(2030, 3, 10), date(2030, 3, 19)) == (
        date(2030, 2, 28),
        date(2030, 3, 9),
    )


def test_xirr_and_dietz():
    rate = analysis.xirr([(date(2030, 1, 1), -1000.0), (date(2031, 1, 1), 1100.0)])
    assert rate == pytest.approx(0.10, abs=1e-4)
    assert analysis.xirr([(date(2030, 1, 1), -1000.0)]) is None
    r = analysis.dietz(
        D("1000"), D("2150"), [(date(2030, 1, 16), D("1000"))], date(2030, 1, 1), date(2030, 1, 30)
    )
    assert float(r) == pytest.approx(0.1, abs=0.002)


def test_a_short_chart_widens_to_twelve_months():
    months, widened = analysis.series_months(date(2030, 10, 1), date(2030, 10, 31))
    assert widened and len(months) == 12 and months[-1] == (2030, 10)
    months, widened = analysis.series_months(date(2030, 1, 1), date(2030, 12, 31))
    assert not widened and len(months) == 12


def test_worth_matches_the_networth_kpi_and_splits_saving_from_return():
    lo = book_with_payrolls()
    w = analysis.worth(lo, date(2030, 10, 1), date(2030, 10, 31), False, False, TODAY)
    networth = next(k for k in compute(lo, date(2030, 10, 31)) if k.key == "networth")
    assert w["total"] == networth.value
    assert "Property" not in w["groups"] and w["groups"][0] == "Cash"
    last = w["points"][-1]
    cash = last["by_group"]["Cash"]
    assert last["contributed"] == cash + D("500")
    assert last["total"] == cash + D("500")
    with_home = analysis.worth(lo, date(2030, 10, 1), date(2030, 10, 31), True, True, TODAY)
    assert "Property" in with_home["groups"]


def test_investments_give_capital_gain_and_xirr_mine_and_the_other_apart():
    lo = book_with_payrolls()
    inv = analysis.investments(lo, date(2030, 10, 1), date(2030, 10, 31), True, False, TODAY)
    fund = next(r for r in inv["rows"] if r["key"] == "fund")
    assert fund["capital"] == D("500") and fund["capital_other"] == D("200")
    assert fund["value"] == D("500") and fund["gain"] == D("0")
    assert fund["contributed_in_period"] == D("300")
    house = next(r for r in inv["rows"] if r["key"] == "house")
    assert house["capital"] == D("500")
    assert inv["contributions"]["labels"] == ["2030-10"]
    without = analysis.investments(lo, date(2030, 10, 1), date(2030, 10, 31), False, False, TODAY)
    assert all(r["key"] != "house" for r in without["rows"])


def test_worth_and_investments_narrow_to_the_chosen_types_and_accounts():
    lo = book_with_payrolls()
    span = (date(2030, 10, 1), date(2030, 10, 31))
    full = analysis.worth(lo, *span, True, False, TODAY)
    funds = analysis.worth(lo, *span, True, False, TODAY, groups={"Funds"})
    assert [r["key"] for r in funds["rows"]] == ["fund"]
    assert funds["groups"] == ["Funds"]
    assert funds["total"] == next(r for r in full["rows"] if r["key"] == "fund")["value"]
    assert funds["points"][-1]["contributed"] == D("500")
    one = analysis.worth(lo, *span, True, False, TODAY, only={"main", "joint"})
    assert {r["key"] for r in one["rows"]} == {"main", "joint"}
    both = analysis.worth(lo, *span, True, False, TODAY, groups={"Funds"}, only={"main"})
    assert both["rows"] == [] and both["total"] == D("0")

    inv = analysis.investments(lo, *span, True, False, TODAY, only={"fund"})
    assert [r["key"] for r in inv["rows"]] == ["fund"]
    assert inv["total"]["capital"] == D("500") and inv["total"]["value"] == D("500")
    assert [s["key"] for s in inv["contributions"]["series"]] == ["fund"]
    home = analysis.investments(lo, *span, True, False, TODAY, groups={"Property"})
    assert [r["key"] for r in home["rows"]] == ["house"]


def test_spending_by_category_against_the_previous_period():
    lo = book_with_payrolls()
    s = analysis.spending(lo, date(2030, 10, 1), date(2030, 10, 31), "all", False, "all", TODAY)
    by = {(r["ownership"], r["name"]): r for r in s["rows"]}
    assert by[("shared", "Groceries")]["total"] == D("150")
    assert by[("shared", "Rent")]["total"] == D("500")
    assert by[("individual", "Leisure")]["total"] == D("60")
    assert s["total"] == D("710") and s["groups"]["not_basic"] == D("60")
    assert s["previous_period"] == {"from": date(2030, 9, 1), "to": date(2030, 9, 30)}
    whole = analysis.spending(
        lo, date(2030, 10, 1), date(2030, 10, 31), "shared", True, "all", TODAY
    )
    assert whole["total"] == D("1200")
    basic = analysis.spending(
        lo, date(2030, 10, 1), date(2030, 10, 31), "all", False, "basic", TODAY
    )
    assert basic["total"] == D("650")
    assert analysis.individual_months(lo, date(2030, 7, 1), date(2030, 8, 31)) == 1


def test_spending_averages_leave_out_the_month_in_course():
    lo = book_with_payrolls()
    october = analysis.spending(
        lo, date(2030, 10, 1), date(2030, 10, 31), "all", False, "all", TODAY
    )
    ongoing = analysis.spending(
        lo, date(2030, 10, 1), date(2030, 11, 30), "all", False, "all", TODAY
    )
    assert ongoing["months"] == 2 and ongoing["closed_months"] == 1
    assert ongoing["monthly"] == october["total"]
    by = {r["key"]: r for r in ongoing["rows"]}
    assert by["individual:Leisure"]["average"] == D("60")
    assert ongoing["usual_months"] == october["usual_months"]
    only_now = analysis.spending(
        lo, date(2030, 11, 1), date(2030, 11, 30), "all", False, "all", TODAY
    )
    assert only_now["closed_months"] == 0 and only_now["monthly"] is None
    assert all(r["average"] is None for r in only_now["rows"])


def test_a_category_shows_its_movements_and_what_only_the_history_knows():
    lo = book_with_payrolls()
    d = analysis.category_detail(
        lo, date(2030, 8, 1), date(2030, 10, 31), "Groceries", "shared", False
    )
    assert [m["id"] for m in d["movements"]] == ["super"] and d["movements"][0]["amount"] == D(
        "150"
    )
    assert d["history"] == D("300")


def test_payroll_cycles_start_at_each_payroll_and_belong_to_the_month_of_most_of_their_days():
    lo = book_with_payrolls()
    assert analysis.payroll_days(lo) == [date(2030, 9, 28), date(2030, 10, 29)]
    seg = analysis.segments(lo, True, TODAY)
    book = [s for s in seg if s.kind == "cycle"]
    assert [(s.start, s.end, s.month) for s in book] == [
        (date(2030, 9, 1), date(2030, 9, 27), (2030, 9)),
        (date(2030, 9, 28), date(2030, 10, 28), (2030, 10)),
        (date(2030, 10, 29), date(2030, 11, 10), (2030, 11)),
    ]
    assert book[-1].open
    assert all(s.kind == "month" for s in seg if s.start < CUTOFF)


def test_the_flow_balances_and_sends_what_was_paid_to_the_home_to_investment():
    lo = book_with_payrolls()
    f = analysis.flow(lo, date(2030, 10, 1), date(2030, 10, 31), True, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in f["links"]}
    assert f["segments"][0]["from"] == date(2030, 9, 28)
    assert links[("in:Salary", "you")] == D("2005")
    assert links[("spent", "spent:Leisure")] == D("60")
    assert links[("common", "common:Groceries")] == D("150")
    assert ("common", "common:Rent") not in links
    assert links[("invest", "invest:house")] == D("500")
    assert links[("invest", "invest:fund")] == D("300")
    inflow = sum(v for (s, t), v in links.items() if t == "you")
    outflow = sum(v for (s, t), v in links.items() if s == "you")
    assert inflow == outflow
    whole = analysis.flow(lo, date(2030, 10, 1), date(2030, 10, 31), True, True, TODAY)
    member = next(k for k in whole["links"] if k["source"] == "member")
    assert member["value"] == D("50") + D("500")


def test_each_cycle_runs_from_its_payroll_and_is_the_month_it_pays():
    lo = book_with_payrolls()
    october = analysis.flow(lo, date(2030, 10, 1), date(2030, 10, 31), True, False, TODAY)
    assert [(s["from"], s["to"]) for s in october["segments"]] == [
        (date(2030, 9, 28), date(2030, 10, 28))
    ]
    assert october["totals"]["income"] == D("2005")
    november = analysis.flow(lo, date(2030, 11, 1), date(2030, 11, 30), True, False, TODAY)
    assert november["segments"][0]["from"] == date(2030, 10, 29)
    assert november["totals"]["income"] == D("2000")


def test_the_first_cycle_after_the_cutoff_carries_the_last_history_payroll():
    lo = book_with_payrolls()
    lo.book.facts.append(Fact("n0", "main", date(2030, 8, 29), D("2500"), "nomina"))
    lo.book.imputations.append(
        Imputation("n0", D("2500"), "income", "individual", "salario", basis="manual")
    )
    august = analysis.flow(lo, date(2030, 8, 1), date(2030, 8, 31), True, False, TODAY)
    september = analysis.flow(lo, date(2030, 9, 1), date(2030, 9, 30), True, False, TODAY)
    assert "in:Salary" not in {link["source"] for link in august["links"]}
    assert [(s["from"], s["to"]) for s in september["segments"]] == [
        (date(2030, 9, 1), date(2030, 9, 27))
    ]
    assert september["totals"]["income"] == D("2000")
    assert september["payroll_moved"] == {"in": D("2000"), "out": D("0")}


def test_the_rent_paid_to_the_home_can_be_read_as_shared_spending():
    lo = book_with_payrolls()
    f = analysis.flow(
        lo, date(2030, 10, 1), date(2030, 10, 31), True, False, TODAY, rent_invested=False
    )
    links = {(k["source"], k["target"]): k["value"] for k in f["links"]}
    assert links[("common", "common:Rent")] == D("500")
    assert ("invest", "invest:house") not in links
    assert links[("invest", "invest:fund")] == D("300")
    inflow = sum(v for (s, t), v in links.items() if t == "you")
    outflow = sum(v for (s, t), v in links.items() if s == "you")
    assert inflow == outflow
    invested = analysis.flow(lo, date(2030, 10, 1), date(2030, 10, 31), True, False, TODAY)
    assert f["totals"]["left"] == invested["totals"]["left"]


def test_what_was_left_in_a_history_month_without_personal_spending_is_unlabelled_spending():
    lo = book_with_payrolls()
    lo.flows.extend(
        [
            Flow(2030, 7, "income", D("2000"), "Salary"),
            Flow(2030, 7, "contribution", D("300"), account="fund"),
        ]
    )
    lo.history.append(
        HistoryRow(2030, 7, "expense", D("400"), "Groceries", "proportional", "account")
    )
    july = analysis.flow(lo, date(2030, 7, 1), date(2030, 7, 31), False, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in july["links"]}
    assert july["unlogged"] == 1
    assert links[("spent", "spent:Unlabelled")] == D("2000") - D("300") - D("300")
    assert july["totals"]["left"] == 0
    whole = analysis.flow(lo, date(2030, 7, 1), date(2030, 7, 31), False, True, TODAY)
    assert whole["totals"]["spent"] == july["totals"]["spent"]
    august = analysis.flow(lo, date(2030, 8, 1), date(2030, 8, 31), False, False, TODAY)
    assert "spent:Unlabelled" not in {n["id"] for n in august["nodes"]}


def test_what_was_missing_in_a_history_month_without_personal_spending_never_comes_from_savings():
    lo = book_with_payrolls()
    lo.flows.extend(
        [
            Flow(2030, 6, "income", D("1000"), "Salary"),
            Flow(2030, 6, "contribution", D("1500"), account="fund"),
            Flow(2030, 7, "income", D("2000"), "Salary"),
            Flow(2030, 7, "contribution", D("300"), account="fund"),
        ]
    )
    lo.history.append(
        HistoryRow(2030, 7, "expense", D("400"), "Groceries", "proportional", "account")
    )
    both = analysis.flow(lo, date(2030, 6, 1), date(2030, 7, 31), False, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in both["links"]}
    assert both["unlogged"] == 2
    assert links[("spent", "spent:Unlabelled")] == D("1400") - D("500")
    assert "deficit" not in {n["id"] for n in both["nodes"]}
    assert both["totals"]["left"] == 0

    june = analysis.flow(lo, date(2030, 6, 1), date(2030, 6, 30), False, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in june["links"]}
    assert links[("in:Unlabelled", "you")] == D("500")
    assert "deficit" not in {n["id"] for n in june["nodes"]}
    assert june["totals"]["left"] == 0
    whole = analysis.flow(lo, date(2030, 6, 1), date(2030, 6, 30), False, True, TODAY)
    assert whole["totals"]["left"] == 0

    span = analysis.flow(lo, date(2030, 6, 1), date(2030, 10, 31), False, False, TODAY)
    rest = [
        analysis.flow(lo, date(2030, m, 1), analysis.month_end(2030, m), False, False, TODAY)
        for m in (8, 9, 10)
    ]
    assert span["totals"]["left"] == sum((r["totals"]["left"] for r in rest), D(0))
    assert span["totals"]["spent"] == D("900") + sum((r["totals"]["spent"] for r in rest), D(0))


def test_by_calendar_month_before_the_cutoff_the_history_counts():
    lo = book_with_payrolls()
    f = analysis.flow(lo, date(2030, 8, 1), date(2030, 8, 31), False, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in f["links"]}
    assert links[("in:Salary", "you")] == D("2000")
    assert links[("common", "common:Groceries")] == D("300")
    assert links[("invest", "invest:fund")] == D("200")
    assert f["totals"]["left"] == D("2000") - D("100") - D("300") - D("200")


def test_the_rent_paid_to_the_home_counts_once_in_the_history_and_without_saying_where():
    lo = book_with_payrolls()
    lo.flows.extend(
        [
            Flow(2030, 8, "contribution", D("500"), account="house"),
            Flow(2030, 8, "contribution", D("500"), account="house", mine=False),
            Flow(2030, 7, "contribution", D("20000"), account="house"),
        ]
    )
    lo.history.extend(
        [
            HistoryRow(2030, 8, "expense", D("1000"), "Rent", "fifty_fifty", "account"),
            HistoryRow(2030, 7, "expense", D("1000"), "Rent", "fifty_fifty", "account"),
        ]
    )
    august = analysis.flow(lo, date(2030, 8, 1), date(2030, 8, 31), False, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in august["links"]}
    assert ("common", "common:Rent") not in links
    assert links[("invest", "invest:house")] == D("500")
    whole = analysis.flow(lo, date(2030, 8, 1), date(2030, 8, 31), False, True, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in whole["links"]}
    assert ("common", "common:Rent") not in links
    assert links[("invest", "invest:house")] == D("1000")

    july = analysis.flow(lo, date(2030, 7, 1), date(2030, 7, 31), False, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in july["links"]}
    assert ("common", "common:Rent") not in links
    assert links[("invest", "invest:house")] == D("20000")
    assert july["unlogged"] == 1

    lo = book_with_payrolls()
    lo.book.facts.append(Fact("casa2", "joint", date(2030, 10, 9), D("-1000"), "virgen"))
    lo = loaded(
        lo.book.facts,
        [
            *[
                Label(f, tuple(i for i in lo.book.imputations if i.fact == f))
                for f in {i.fact for i in lo.book.imputations}
            ],
            label("casa2", "-1000", "alquiler", "expense", "shared", "account"),
        ],
        lo.flows,
        lo.valuations,
        lo.history,
    )
    f = analysis.flow(lo, date(2030, 10, 1), date(2030, 10, 31), True, False, TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in f["links"]}
    assert ("common", "common:Rent") not in links
    assert links[("invest", "invest:house")] == D("1000")
    house = [c for c in analysis.contributions(lo) if c.account == "house"]
    assert sum(c.amount for c in house) == D("2000")


def test_the_circuit_joins_accounts_by_what_passed_between_them():
    lo = book_with_payrolls()
    c = analysis.circuit(lo, date(2030, 10, 1), date(2030, 10, 31), TODAY)
    links = {(k["source"], k["target"]): k for k in c["links"]}
    assert links[("acc:main", "acc:fund")]["value"] == D("300")
    assert links[("in:Salary", "acc:main")]["value"] == D("2005")
    assert links[("acc:main", "out:individual")]["value"] == D("60")
    assert links[("acc:joint", "out:shared")]["value"] == D("200")
    assert c["balances"]["acc:fund"]["end"] == D("1000")
    nodes = {n["id"]: n for n in c["nodes"]}
    assert nodes["acc:main"]["outflow"] == D("1360")
    assert nodes["in:Salary"]["column"] == 0 and nodes["acc:main"]["column"] == 1
    assert nodes["acc:joint"]["column"] == 2 and nodes["acc:fund"]["column"] == 2
    assert nodes["out:individual"]["column"] == 3


def test_the_circuit_shows_who_paid_off_the_bank_and_whose_refund_it_was():
    lo = book_with_payrolls()
    facts = [
        *lo.book.facts,
        Fact("dev", "main", date(2030, 10, 12), D("30"), "devolucion super"),
        Fact("efectivo", OTHER, date(2030, 10, 13), D("-80"), "shopping", "manual", by_other=True),
    ]
    lo = loaded(
        facts,
        [
            *[
                Label(f, tuple(i for i in lo.book.imputations if i.fact == f))
                for f in {i.fact for i in lo.book.imputations}
            ],
            label("dev", "30", "super", "expense", "shared", "account"),
            label("efectivo", "-80", "super", "expense", "shared", "other"),
        ],
        lo.flows,
        lo.valuations,
        lo.history,
    )
    c = analysis.circuit(lo, date(2030, 10, 1), date(2030, 10, 31), TODAY)
    links = {(k["source"], k["target"]): k["value"] for k in c["links"]}
    assert links[("in:refund:shared", "acc:main")] == D("30")
    assert links[("member", "out:shared")] == D("80")


async def test_every_analysis_endpoint_answers_on_an_empty_book(api) -> None:
    period = {"from": "2030-01-01", "to": "2030-12-31"}
    for path in ("worth", "investments", "spending", "flow", "circuit"):
        response = await api.get(f"/analysis/{path}", params=period)
        assert response.status_code == 200, (path, response.text)
    detail = await api.get(
        "/analysis/spending/category",
        params={**period, "name": "Leisure", "ownership": "individual"},
    )
    assert detail.status_code == 200
    narrowed = await api.get(
        "/analysis/investments",
        params={**period, "group": ["Funds", "Crypto"], "account": ["fondo"]},
    )
    assert narrowed.status_code == 200 and narrowed.json()["rows"] == []
    wrong = await api.get("/analysis/worth", params={"from": "2030-02-01", "to": "2030-01-01"})
    assert wrong.status_code == 422
