from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from money.interpret import Interpreter, Label, Rule, merchant_key
from money.ledger import balance_check, statuses
from money.model import OTHER, Account, Balance, Book, Category, Fact, Imputation
from money.shared import (
    HistoryRow,
    Income,
    Month,
    from_book,
    from_history,
    monthly_average,
    ratio,
    year_balance,
)


def acc(id, inst, cls, movements, value, **kw) -> Account:
    return Account(id, id.title(), inst, cls, cls, movements, value, **kw)


ACCOUNTS = {
    a.id: a
    for a in [
        acc("main", "Bank A", "cash", "api", "balance", internal="^TRASPASO INTERNO"),
        acc(
            "joint",
            "Bank A",
            "cash",
            "api",
            "balance",
            ownership=D("0.5"),
            shared_space=True,
            internal="^TRASPASO INTERNO",
        ),
        acc("cashpoint", "Bank B", "cash", "api", "balance"),
        acc("savings", "Bank C", "cash", "matched", "computed", spending=False),
        acc(
            "fund",
            "Manager",
            "investment",
            "statement",
            "snapshot",
            counts_for_savings=True,
            ibans=("ES00FONDO",),
        ),
        acc(
            "home_fund",
            "Manager",
            "investment",
            "statement",
            "snapshot",
            ownership=D("0.5"),
            counts_for_savings=True,
            ibans=("ES00VIVIENDA",),
        ),
    ]
}

CATS = {
    c.id: c
    for c in [
        Category("salary", "Salary", "income", "individual"),
        Category("leisure", "Leisure", "expense", "individual"),
        Category("subs", "Subscriptions", "expense", "individual"),
        Category("rent", "Rent", "expense", "shared", "fifty_fifty"),
        Category("groceries", "Groceries", "expense", "shared", "proportional"),
        Category("utilities", "Utilities", "expense", "shared", "proportional"),
        Category("others", "Other", "expense", "shared", "proportional"),
    ]
}


def f(id, account, day, amount, text, **kw) -> Fact:
    return Fact(id, account, date(2030, 3, day), D(amount), text, **kw)


FACTS = [
    f("salary", "main", 28, "2000", "ABONO DE NOMINA ACME", counterparty="ACME SL"),
    f("to_joint", "main", 1, "-300", "TRASPASO INTERNO A CUENTA", counterparty="ANA TITULAR"),
    f("from_me", "joint", 1, "300", "TRASPASO INTERNO DESDE CUENTA", counterparty="ANA TITULAR"),
    f("from_other", "joint", 2, "300", "TRASPASO DESDE CUENTA", counterparty="BEA PAREJA"),
    f("market", "joint", 5, "-200", "PAGO CON TARJETA // MERCADONA 0231"),
    f("bar", "joint", 9, "-60", "PAGO CON TARJETA // BAR PEPE"),
    f("cinema", "main", 12, "-40", "CINES YELMO"),
    f("refund", "main", 13, "15", "BIZUM DE LUIS cena"),
    f("netflix", "main", 15, "-12.99", "NETFLIX.COM"),
    f("atm", "cashpoint", 1, "-430", "TJ-CAJERO"),
    f(
        "to_savings",
        "main",
        20,
        "-100",
        "TRANSFERENCIA // BANCO C - ANA TITULAR",
        counterparty="BANCO C - ANA TITULAR",
    ),
    f("savings_in", "savings", 21, "100", "TRF. ANA TITULAR"),
    f(
        "to_fund",
        "main",
        29,
        "-300",
        "TRANSFERENCIA // Manager - Alex",
        counterparty_iban="ES00FONDO",
    ),
    f("other_fund", "home_fund", 29, "200", "Partner contribution", source="statement"),
    f("other_rent", OTHER, 1, "-400", "Rent, their half", source="manual", by_other=True),
]

RULES = [
    Rule(account="joint", counterparty="BEA PAREJA", sign=1, from_other_member=True),
    Rule(account="home_fund", sign=1, from_other_member=True),
    Rule(text="ABONO DE NOMINA", category="salary"),
    Rule(text="CAJERO", sign=-1, ask=True),
    Rule(merchant="MERCADONA", category="groceries"),
    Rule(merchant="CINES YELMO", category="leisure"),
    Rule(text="BIZUM DE .* cena", sign=1, category="leisure"),
    Rule(text="NETFLIX", category="subs"),
    Rule(account="joint", category="others", basis="default"),
]

LABELS = [
    Label(
        "atm",
        (
            Imputation("atm", D("-400"), "expense", "shared", "rent", "me"),
            Imputation("atm", D("-30"), "expense", "shared", "utilities", "me"),
        ),
    ),
    Label(
        "other_rent", (Imputation("other_rent", D("-400"), "expense", "shared", "rent", "other"),)
    ),
]

MERCHANTS = {"market": "MERCADONA 0231", "bar": "BAR PEPE", "cinema": "CINES YELMO"}


def book(labels=LABELS) -> Book:
    interp = Interpreter(
        rules=RULES, labels=list(labels), holders=("ANA TITULAR",), merchant_of=MERCHANTS
    )
    return interp.run(Book(ACCOUNTS, CATS, list(FACTS)))


def test_every_fact_ends_as_exactly_one_thing():
    s = statuses(book())
    assert s == {
        "salary": "auto",
        "to_joint": "transfer",
        "from_me": "transfer",
        "from_other": "transfer",
        "market": "auto",
        "bar": "default",
        "cinema": "auto",
        "refund": "auto",
        "netflix": "auto",
        "atm": "manual",
        "to_savings": "transfer",
        "savings_in": "transfer",
        "to_fund": "transfer",
        "other_fund": "transfer",
        "other_rent": "manual",
    }


def test_cash_waits_for_the_person_until_it_is_labelled():
    assert statuses(book(labels=LABELS[1:]))["atm"] == "ask"


def test_transfers_carry_no_category():
    b = book()
    assert not [i for i in b.imputations if i.fact in b.transferred()]


def test_iban_names_the_fund_even_without_its_statement():
    b = book()
    t = next(t for t in b.transfers if t.out_fact == "to_fund")
    assert b.fact(t.in_fact).account == "fund" and t.basis == "inferred"


def test_a_refund_reduces_its_category():
    b = book()
    leisure = sum(-i.amount for i in b.imputations if i.category == "leisure")
    assert leisure == D("25")


def test_someone_else_with_the_same_amount_is_not_my_transfer():
    b = book()
    assert ("to_joint", "from_me") in {(t.out_fact, t.in_fact) for t in b.transfers}
    assert not any(t.out_fact and t.in_fact == "from_other" for t in b.transfers)


def test_iban_decides_between_same_day_twins():
    facts = [
        f("a", "main", 29, "-250", "Manager - Alex", counterparty_iban="ES00VIVIENDA"),
        f("b", "main", 29, "-250", "Manager - Alex", counterparty_iban="ES00FONDO"),
        f("c", "fund", 30, "250", "entrada"),
        f("d", "home_fund", 30, "250", "entrada"),
    ]
    b = Interpreter().run(Book(ACCOUNTS, CATS, facts))
    assert {(t.out_fact, t.in_fact) for t in b.transfers} == {("a", "d"), ("b", "c")}


def test_without_evidence_two_institutions_are_too_many():
    facts = [
        f("a", "main", 5, "-100", "X"),
        f("b", "savings", 4, "100", "Y"),
        f("c", "cashpoint", 6, "100", "Z"),
    ]
    assert Interpreter().run(Book(ACCOUNTS, CATS, facts)).transfers == []


def test_merchant_rules_ignore_numbers_and_accents():
    assert merchant_key("Mercadona 0231 Avda. S\u00e1nchez") == merchant_key(
        "MERCADONA AVDA SANCHEZ"
    )


def test_a_label_wins_over_any_rule():
    labelled = [
        Label("netflix", (Imputation("netflix", D("-12.99"), "expense", "individual", "leisure"),))
    ]
    b = book(labels=LABELS + labelled)
    assert [i.category for i in b.imputations if i.fact == "netflix"] == ["leisure"]


def test_a_settlement_is_neither_expense_nor_income():
    b = book(labels=LABELS + [Label("cinema", settlement=True)])
    assert "cinema" in b.settlements and not [i for i in b.imputations if i.fact == "cinema"]


def test_a_transfer_told_by_hand_infers_the_other_side_until_it_arrives():
    came = f("came", "main", 10, "100", "TRANSFERENCIA RECIBIDA // Plan de pensiones")
    said = Label("came", transfer_with="savings")
    b = Interpreter(labels=[said]).run(Book(ACCOUNTS, CATS, [came]))
    t = next(t for t in b.transfers if t.in_fact == "came")
    assert t.basis == "inferred" and b.fact(t.out_fact).account == "savings"
    assert statuses(b)["came"] == "transfer"
    assert not [i for i in b.imputations if i.fact == "came"]

    real = f("left", "savings", 9, "-100", "Transfer to another institution", source="statement")
    b = Interpreter(labels=[said]).run(Book(ACCOUNTS, CATS, [came, real]))
    assert [(t.out_fact, t.in_fact, t.basis) for t in b.transfers] == [("left", "came", "manual")]
    assert not [x for x in b.facts if x.source == "inferred"]


def test_shared_balance_follows_caudal():
    m = from_book(book(), 2030, 3)
    r = D("0.6")
    assert m.total == D("1090")
    assert (m.deposits_me, m.deposits_other) == (D("300"), D("300"))
    assert (m.paid_me, m.paid_other, m.paid_account) == (D("430"), D("400"), D("260"))
    ob_me = D("800") * D("0.5") + D("290") * r
    assert m.obligation_me(r) == ob_me
    raw_me = D("300") + D("430") - ob_me
    raw_other = D("300") + D("400") - (D("1090") - ob_me)
    assert m.balance_me(r) == (raw_me - raw_other) / 2


def test_closed_months_come_from_history_only():
    rows = [
        HistoryRow(2030, 2, "expense", D("1000"), "Rent", "fifty_fifty", "me"),
        HistoryRow(2030, 2, "deposit", D("100"), payer="other"),
    ]
    m = from_history(rows, 2030, 2)
    assert (m.total, m.paid_me, m.deposits_other, m.source) == (
        D("1000"),
        D("1000"),
        D("100"),
        "history",
    )
    yb = year_balance([m, from_book(book(), 2030, 3)], D("0.6"), 2030)
    assert yb.balance_me == m.balance_me(D("0.6")) + from_book(book(), 2030, 3).balance_me(D("0.6"))


def test_the_shared_monthly_average_leaves_out_the_month_in_course():
    months = [
        Month(2030, 1, "book", {"Grocer": D("300")}),
        Month(2030, 2, "book", {"Grocer": D("500"), "Electricity": D("80")}),
        Month(2030, 3, "book", {"Grocer": D("20")}),
    ]
    assert monthly_average(months, 2030, date(2030, 3, 9)) == (
        2,
        {"Grocer": D("400"), "Electricity": D("40")},
    )
    assert monthly_average(months, 2030, date(2031, 1, 2))[0] == 3
    assert monthly_average(months[:1], 2030, date(2030, 1, 20)) == (0, {})


def test_ratio_weights_each_slice_by_its_days_like_caudal():
    incomes = [
        Income("me", date(2030, 1, 1), date(2030, 12, 31), D("36500")),
        Income("other", date(2030, 1, 1), date(2030, 6, 30), D("36500")),
    ]
    assert ratio(incomes, 2030) == D("36500") / (D("36500") + D("100") * 181)
    assert ratio([], 2030) == D("0.5")


def test_closing_balances_follow_value_dates():
    facts = [f("x", "main", 10, "-50", "algo", value_on=date(2030, 3, 9))]
    b = Book(
        ACCOUNTS,
        CATS,
        facts,
        [
            Balance("main", date(2030, 3, 8), D("100")),
            Balance("main", date(2030, 3, 9), D("50")),
        ],
    )
    assert balance_check(b, ACCOUNTS["main"], date(2030, 3, 1), date(2030, 3, 31)).ok


def test_a_held_card_charge_reads_as_a_missing_charge_of_its_own_amount():
    facts = [
        f("a", "main", 11, "-30", "tren"),
        f("b", "main", 11, "-40.24", "bizum"),
    ]
    b = Book(
        ACCOUNTS,
        CATS,
        facts,
        [
            Balance("main", date(2030, 3, 11), D("122.29"), "available"),
            Balance("main", date(2030, 3, 12), D("11.65"), "available"),
        ],
    )
    check = balance_check(b, ACCOUNTS["main"], date(2030, 3, 1), date(2030, 3, 31))
    assert not check.ok
    assert check.gap == D("40.40")
    b.facts.append(f("c", "main", 12, "-40.40", "cargo retenido"))
    assert balance_check(b, ACCOUNTS["main"], date(2030, 3, 1), date(2030, 3, 31)).ok
