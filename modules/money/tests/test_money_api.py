from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from money_people import OTHER, PERSON
from sqlalchemy import text

from arga_tenancy import SPACES_HEADER, USER_HEADER, current_user
from money import tools

BANK = "Bank One"
MAIN, JOINT = "src-main", "src-joint"


def event(type_: str, payload: dict, dedup: str, module: str = "hub") -> dict:
    return {"type": type_, "payload": payload, "dedup": dedup, "module": module}


def movement(
    account: str, ref: str, day: str, amount: str, description: str, **detail
) -> list[dict]:
    out = [
        event(
            "finance.movement",
            {
                "account": account,
                "reference": ref,
                "booked_on": day,
                "value_on": day,
                "amount": amount,
                "currency": "EUR",
                "description": description,
            },
            f"bank:{account}:{ref}",
        )
    ]
    if detail:
        out.append(
            event(
                "finance.movement_detail",
                {"account": account, "reference": ref, **detail},
                f"bank:{account}:{ref}:detail",
            )
        )
    return out


EVENTS = [
    event(
        "finance.account",
        {
            "account": MAIN,
            "bank": BANK,
            "name": "TITULAR UNO",
            "kind": "checking",
            "iban_tail": "1111",
            "iban": "ES0000000000000000001111",
        },
        "acc-main",
    ),
    event(
        "finance.account",
        {
            "account": JOINT,
            "bank": BANK,
            "name": "TITULAR UNO",
            "kind": "checking",
            "iban_tail": "2222",
            "iban": "ES0000000000000000002222",
        },
        "acc-joint",
    ),
    *movement(
        MAIN,
        "m1",
        "2026-03-28",
        "2000.00",
        "ABONO DE NOMINA // EMPRESA INVENTADA SL",
        counterparty_name="EMPRESA INVENTADA SL",
    ),
    *movement(
        MAIN,
        "m2",
        "2026-03-01",
        "-300.00",
        "TRASPASO // TRASPASO A CUENTA // TITULAR UNO",
        counterparty_name="TITULAR UNO",
        counterparty_iban="ES0000000000000000002222",
    ),
    *movement(
        JOINT,
        "j1",
        "2026-03-01",
        "300.00",
        "TRASPASO // TRASPASO DESDE CUENTA // TITULAR UNO",
        counterparty_name="TITULAR UNO",
    ),
    *movement(
        JOINT,
        "j2",
        "2026-03-02",
        "300.00",
        "TRASPASO // TRASPASO DESDE CUENTA // PAREJA DOS",
        counterparty_name="PAREJA DOS",
    ),
    *movement(
        JOINT,
        "j3",
        "2026-03-05",
        "-200.00",
        "PAGO CON TARJETA EN SUPERMERCADOS // PAGO CON TARJETA // SUPER INVENTADO 01  CIUDAD",
    ),
    *movement(
        JOINT,
        "j4",
        "2026-03-08",
        "-40.00",
        "PAGO CON TARJETA EN SUPERMERCADOS // PAGO CON TARJETA // SUPER INVENTADO 02  CIUDAD",
    ),
    *movement(
        JOINT,
        "j5",
        "2026-03-09",
        "-60.00",
        "PAGO CON TARJETA EN RESTAURANTES // PAGO CON TARJETA // BAR INVENTADO  CIUDAD",
    ),
    *movement(
        MAIN, "m3", "2026-03-10", "-430.00", "RET. EFECTIVO A DEBITO // OTROS // CAJERO 0001"
    ),
    event(
        "money.movement",
        {
            "account": MAIN,
            "reference": "old1",
            "booked_on": "2026-03-15",
            "value_on": "2026-03-15",
            "amount": "-12.99",
            "currency": "EUR",
            "description": "PLATAFORMA DE SERIES",
        },
        f"bank:{MAIN}:old1",
        module="money",
    ),
]

BUNDLE = {
    "settings": {
        "cutoff": "2026-03-01",
        "me_name": "One",
        "other_name": "Two",
        "holders": ["TITULAR UNO"],
    },
    "accounts": [
        {
            "key": "main",
            "name": "Main",
            "institution": "BBVA",
            "type": "current",
            "movements": "api",
            "match": {"bank": BANK, "key": "1111"},
        },
        {
            "key": "joint",
            "name": "Shared",
            "institution": "BBVA",
            "type": "current",
            "movements": "api",
            "ownership": 0.5,
            "shared_space": True,
            "match": {"bank": BANK, "key": "2222"},
        },
    ],
    "categories": [
        {"nature": "income", "ownership": "individual", "name": "Salary"},
        {"nature": "expense", "ownership": "individual", "name": "Subscriptions"},
        {"nature": "expense", "ownership": "shared", "name": "Rent", "split": "fifty_fifty"},
        {
            "nature": "expense",
            "ownership": "shared",
            "name": "Groceries",
            "split": "proportional",
        },
        {
            "nature": "expense",
            "ownership": "shared",
            "name": "Utilities",
            "split": "proportional",
        },
        {"nature": "expense", "ownership": "shared", "name": "Other", "split": "proportional"},
    ],
    "rules": [
        {"account": "joint", "counterparty": "PAREJA DOS", "sign": 1, "from_other_member": True},
        {"text": "ABONO DE NOMINA", "category": "income/individual/Salary"},
        {"text": "CAJERO", "sign": -1, "ask": True},
        {
            "account": "joint",
            "bank_category": "SUPERMERCADOS",
            "category": "expense/shared/Groceries",
            "basis": "bank",
        },
        {"account": "joint", "category": "expense/shared/Other", "basis": "default"},
    ],
    "incomes": [
        {"person": "me", "from": "2026-01-01", "to": "2026-12-31", "salary": 30000},
        {"person": "other", "from": "2026-01-01", "to": "2026-12-31", "salary": 20000},
    ],
    "years": {"2025": True},
    "history": [
        {
            "year": 2026,
            "month": 2,
            "kind": "expense",
            "amount": 1000,
            "category": "Rent",
            "split": "fifty_fifty",
            "payer": "account",
        },
        {"year": 2026, "month": 2, "kind": "deposit", "amount": 450, "payer": "me"},
        {"year": 2026, "month": 2, "kind": "deposit", "amount": 550, "payer": "other"},
    ],
}


@pytest.fixture
async def book(schema, api):
    async with schema.begin() as connection:
        await connection.execute(
            text("delete from kernel.events where user_id = any(:u)"), {"u": [PERSON, OTHER]}
        )
        for e in EVENTS:
            await connection.execute(
                text("""
                insert into kernel.events (ts, module, source, type, payload, dedup_hash, user_id)
                values (:ts, :m, 'bank', :t, cast(:p as jsonb), :d, :u)
            """),
                {
                    "ts": datetime.now(UTC),
                    "m": e["module"],
                    "t": e["type"],
                    "p": json.dumps(e["payload"]),
                    "d": e["dedup"],
                    "u": PERSON,
                },
            )
    response = await api.post("/import", json=BUNDLE)
    assert response.status_code == 200, response.text
    yield api
    async with schema.begin() as connection:
        await connection.execute(
            text("delete from kernel.events where user_id = any(:u)"), {"u": [PERSON, OTHER]}
        )


async def march(api) -> dict[str, dict]:
    response = await api.get("/movements", params={"from": "2026-03-01", "to": "2026-03-31"})
    assert response.status_code == 200, response.text
    return {m["id"]: m for m in response.json()["movements"]}


async def test_the_import_sets_up_accounts_and_categories(book) -> None:
    state = (await book.get("/state")).json()
    assert state["configured"] and state["me"] == "One" and state["other"] == "Two"
    assert {a["key"] for a in state["accounts"]} == {"main", "joint"}
    assert len(state["categories"]) == 6 and state["unmapped"] == []


async def test_every_movement_is_read_including_the_old_connector(book) -> None:
    rows = await march(book)
    assert rows["main:m1"]["status"] == "auto" and rows["main:m1"]["kind"] == "income"
    assert (
        rows["main:m2"]["status"] == "transfer"
        and rows["main:m2"]["transfer"]["account"] == "joint"
    )
    assert (
        rows["joint:j2"]["status"] == "transfer" and rows["joint:j2"]["transfer"]["account"] is None
    )
    assert rows["joint:j3"]["parts"][0]["category_name"] == "Groceries"
    assert rows["joint:j3"]["merchant"] == "SUPER INVENTADO 01"
    assert rows["joint:j5"]["status"] == "default"
    assert rows["main:m3"]["status"] == "ask"
    assert rows["main:old1"]["status"] == "pending"


async def test_cash_is_labelled_in_parts_and_back_to_automatic(book) -> None:
    state = (await book.get("/state")).json()
    cat = {c["name"]: c["id"] for c in state["categories"]}
    parts = {
        "parts": [
            {"amount": "400", "category": cat["Rent"]},
            {"amount": "30", "category": cat["Utilities"]},
        ]
    }
    response = await book.put("/label", params={"id": "main:m3"}, json=parts)
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "manual" and [p["amount"] for p in out["parts"]] == [-400.0, -30.0]
    assert {p["payer"] for p in out["parts"]} == {"me"}

    wrong = {"parts": [{"amount": "100", "category": cat["Rent"]}]}
    assert (await book.put("/label", params={"id": "main:m3"}, json=wrong)).status_code == 422

    back = await book.delete("/label", params={"id": "main:m3"})
    assert back.json()["status"] == "ask"


async def test_a_movement_is_told_to_be_a_transfer_with_another_account(book) -> None:
    state = (await book.get("/state")).json()
    other = next(a["key"] for a in state["accounts"] if a["key"] != "main")
    response = await book.put("/label", params={"id": "main:m3"}, json={"transfer_with": other})
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["status"] == "transfer" and out["labelled"] and out["parts"] == []
    assert out["transfer"]["basis"] == "inferred"

    same = await book.put("/label", params={"id": "main:m3"}, json={"transfer_with": "main"})
    assert same.status_code == 422
    both = {"transfer_with": other, "settlement": True}
    assert (await book.put("/label", params={"id": "main:m3"}, json=both)).status_code == 422

    back = await book.delete("/label", params={"id": "main:m3"})
    assert back.json()["status"] == "ask"


async def test_applying_to_a_merchant_creates_one_rule(book) -> None:
    state = (await book.get("/state")).json()
    subs = next(c["id"] for c in state["categories"] if c["name"] == "Subscriptions")
    response = await book.post(
        "/merchant-rule", params={"id": "main:old1"}, json={"category": subs}
    )
    assert response.status_code == 200, response.text
    rows = await march(book)
    assert rows["main:old1"]["status"] == "auto"
    assert rows["main:old1"]["parts"][0]["category_name"] == "Subscriptions"
    again = await book.post("/merchant-rule", params={"id": "main:old1"}, json={"category": subs})
    assert again.status_code == 200
    assert (await book.get("/state")).json()["rules"] == len(BUNDLE["rules"]) + 1


async def test_shared_year_mixes_history_before_the_cutoff_and_the_book_after(book) -> None:
    state = (await book.get("/state")).json()
    cat = {c["name"]: c["id"] for c in state["categories"]}
    await book.put(
        "/label",
        params={"id": "main:m3"},
        json={"parts": [{"amount": "430", "category": cat["Rent"]}]},
    )
    out = (await book.get("/shared", params={"year": 2026})).json()
    months = {m["month"]: m for m in out["months"]}
    assert months[2]["source"] == "history" and months[3]["source"] == "book"
    assert months[3]["total"] == 730.0
    assert months[3]["deposits"] == {"me": 300.0, "other": 300.0}
    assert months[3]["paid"]["me"] == 430.0
    r = 30000 / 50000
    feb = ((450 - 500) - (550 - 500)) / 2
    ob_me = 430 * 0.5 + 300 * r
    mar = ((300 + 430 - ob_me) - (300 - (730 - ob_me))) / 2
    assert out["ratio_me"] == pytest.approx(r)
    assert out["balance_me"] == pytest.approx(feb + mar, abs=0.01)


async def test_what_the_other_person_pays_counts_as_hers(book) -> None:
    state = (await book.get("/state")).json()
    cat = {c["name"]: c["id"] for c in state["categories"]}
    before = (await book.get("/shared", params={"year": 2026})).json()["balance_me"]
    created = await book.post(
        "/shared/entries",
        json={
            "payer": "other",
            "on": "2026-03-03",
            "amount": "100",
            "description": "Electricity",
            "category": cat["Utilities"],
        },
    )
    assert created.status_code == 201, created.text
    out = (await book.get("/shared", params={"year": 2026})).json()
    assert (
        out["entries"][0]["description"] == "Electricity" and out["entries"][0]["payer"] == "other"
    )
    r = 30000 / 50000
    assert out["balance_me"] == pytest.approx(
        before - (r * 100 + (100 - (100 - r * 100))) / 2, abs=0.01
    )
    gone = await book.delete(f"/shared/entries/{out['entries'][0]['id']}")
    assert gone.status_code == 204
    assert (await book.get("/shared", params={"year": 2026})).json()["balance_me"] == pytest.approx(
        before
    )


async def test_years_and_declared_incomes(book) -> None:
    assert (await book.put("/shared/years/2026", json={"settled": True})).status_code == 200
    assert (await book.get("/shared", params={"year": 2026})).json()["settled"] is True
    response = await book.put(
        "/shared/incomes/2026",
        json={
            "incomes": [
                {"person": "me", "from": "2026-01-01", "to": "2026-12-31", "salary": 25000},
                {"person": "other", "from": "2026-01-01", "to": "2026-12-31", "salary": 25000},
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert (await book.get("/shared", params={"year": 2026})).json()["ratio_me"] == 0.5


async def test_the_export_is_what_was_imported(book) -> None:
    exported = (await book.get("/export")).json()
    assert len(exported["accounts"]) == 2 and len(exported["rules"]) == len(BUNDLE["rules"])
    assert exported["rules"][1]["category"] == "income/individual/Salary"
    again = await book.post("/import", json=exported)
    assert again.status_code == 200, again.text
    assert (await march(book))["main:m1"]["status"] == "auto"


async def test_an_import_naming_a_missing_category_changes_nothing(book) -> None:
    broken = {**BUNDLE, "rules": [{"text": "X", "category": "expense/individual/Does not exist"}]}
    response = await book.post("/import", json=broken)
    assert response.status_code == 422
    assert (await book.get("/state")).json()["rules"] == len(BUNDLE["rules"])


async def test_another_person_sees_nothing(book) -> None:
    token = current_user.set(OTHER)
    try:
        state = (await book.get("/state")).json()
        rows = (
            await book.get("/movements", params={"from": "2026-03-01", "to": "2026-03-31"})
        ).json()
    finally:
        current_user.reset(token)
    assert state["configured"] is False and state["categories"] == []
    assert rows["movements"] == []


async def test_a_movement_that_does_not_exist_is_404(book) -> None:
    assert (await book.get("/movement", params={"id": f"main:{uuid4()}"})).status_code == 404


async def test_the_whole_history_is_kept_month_by_month(book) -> None:
    bundle = {
        **BUNDLE,
        "history_flow": [
            {"year": 2025, "month": 3, "kind": "income", "amount": 1800, "category": "Salary"},
            {"year": 2025, "month": 3, "kind": "expense", "amount": 120, "category": "Leisure"},
            {"year": 2025, "month": 3, "kind": "contribution", "amount": 300, "account": "main"},
            {
                "year": 2025,
                "month": 3,
                "kind": "contribution",
                "amount": 200,
                "account": "main",
                "mine": False,
            },
        ],
        "valuations": [{"account": "main", "on": "2025-03-31", "value": 1234.5}],
    }
    response = await book.post("/import", json=bundle)
    assert response.status_code == 200, response.text
    assert response.json()["history_flow"] == 4 and response.json()["valuations"] == 1
    out = (await book.get("/history", params={"year": 2025})).json()
    march = out["months"][0]
    assert march["month"] == 3
    assert march["income"] == {"Salary": 1800.0} and march["expense"] == {"Leisure": 120.0}
    assert march["contributions"] == {"main": 300.0} and march["others"] == {"main": 200.0}
    assert march["values"] == {"main": 1234.5}
    assert 2025 in (await book.get("/state")).json()["years"]
    exported = (await book.get("/export")).json()
    assert len(exported["history_flow"]) == 4 and exported["valuations"][0]["value"] == 1234.5


async def test_a_contribution_to_a_missing_account_is_refused(book) -> None:
    bundle = {
        **BUNDLE,
        "history_flow": [
            {"year": 2025, "month": 3, "kind": "contribution", "amount": 1, "account": "nobody"}
        ],
    }
    assert (await book.post("/import", json=bundle)).status_code == 422


async def test_the_summary_and_its_widgets_tell_the_same(book) -> None:
    summary = (await book.get("/summary")).json()
    assert [k["key"] for k in summary["kpis"]] == [
        "networth",
        "liquid",
        "cash",
        "emergency",
        "expense",
        "basic",
    ]
    assert summary["emergency_months"] == 3
    expense = next(k for k in summary["kpis"] if k["key"] == "expense")
    widget = (await book.get("/widgets/expense")).json()
    assert widget["state"] == "ready" and widget["body"]["value"] == expense["value"]
    assert widget["body"]["previous"] == 0
    fund = (await book.get("/widgets/emergency")).json()
    assert fund["state"] == "empty"


async def test_the_emergency_fund_is_chosen_and_its_months_set(book) -> None:
    response = await book.put(
        "/settings", json={"emergency_months": 6, "emergency_account": "main"}
    )
    assert response.status_code == 200, response.text
    state = (await book.get("/state")).json()
    assert [a["key"] for a in state["accounts"] if a["role"] == "emergency_fund"] == ["main"]
    summary = (await book.get("/summary")).json()
    assert summary["emergency_months"] == 6
    fund = next(k for k in summary["kpis"] if k["key"] == "emergency")
    assert fund["value"] is not None
    bad = await book.put("/settings", json={"emergency_months": 6, "emergency_account": "nobody"})
    assert bad.status_code == 422


async def test_the_balance_widget_asks_which_account(book) -> None:
    options = (await book.get("/widgets/account/options")).json()
    assert {o["value"] for o in options} == {"main", "joint"}
    empty = (await book.get("/widgets/account/value")).json()
    assert empty["state"] == "empty"
    one = (await book.get("/widgets/account/value", params={"option": "main"})).json()
    assert one["state"] in ("ready", "empty") and "Main" in one["body"]["detail"]


async def test_the_shared_widget_says_what_the_open_years_owe(book) -> None:
    years = (await book.get("/state")).json()["years"]
    owed, open_years = 0.0, []
    for year in years:
        shared = (await book.get("/shared", params={"year": year})).json()
        if not shared["settled"] and (shared["total"] or shared["balance_me"]):
            owed += shared["balance_me"]
            open_years.append(year)
    assert open_years
    widget = (await book.get("/widgets/shared")).json()
    assert widget["state"] == "ready"
    assert widget["body"]["value"] == pytest.approx(owed, abs=0.01)
    for year in open_years:
        await book.put(f"/shared/years/{year}", json={"settled": True})
    settled = (await book.get("/widgets/shared")).json()
    assert settled["body"] == {"value": 0, "unit": "€", "detail": "All settled"}


async def test_what_the_hub_reads_from_the_text_wins_over_the_old_catalogue(book, schema) -> None:
    [new] = movement(JOINT, "j9", "2026-03-20", "-25.00", "TEXTO QUE MONEY NO SABE LEER")
    new["payload"] |= {"merchant": "Hub shop", "bank_category": "SUPERMERCADOS"}
    async with schema.begin() as connection:
        await connection.execute(
            text("""
            insert into kernel.events (ts, module, source, type, payload, dedup_hash, user_id)
            values (now(), 'hub', 'bank', :t, cast(:p as jsonb), :d, :u)
        """),
            {"t": new["type"], "p": json.dumps(new["payload"]), "d": new["dedup"], "u": PERSON},
        )

    rows = await march(book)

    assert rows["joint:j9"]["merchant"] == "Hub shop"
    assert rows["joint:j9"]["parts"][0]["category_name"] == "Groceries"


HOME = UUID("00000000-0000-4000-8000-0000000ca5a0")


async def test_a_year_counts_the_incomes_typed_for_it(book) -> None:
    out = (await book.get("/shared", params={"year": 2026})).json()
    assert out["income_totals"] == {"me": 30000.0, "other": 20000.0}
    assert out["ratio_me"] == pytest.approx(0.6)
    assert "carrera" not in out


async def test_the_tool_says_what_each_income_counts(book, schema) -> None:
    async with schema.connect() as connection:
        await connection.execute(text('set role "mod_money_read"'))
        found = await tools.get_shared_balance(connection, tools.GetSharedBalance(year=2026))
    assert [one["amount"] for one in found["incomes"].values()] == [30000.0, 20000.0]


def who(person: UUID, *spaces: UUID) -> dict[str, str]:
    headers = {USER_HEADER: str(person)}
    if spaces:
        headers[SPACES_HEADER] = ",".join(str(one) for one in spaces)
    return headers


async def test_a_space_you_are_not_in_cannot_be_chosen(book) -> None:
    refused = await book.put("/shared/space", json={"space_id": str(HOME)}, headers=who(PERSON))
    assert refused.status_code == 404


async def test_an_account_is_renamed_retyped_and_shared_from_settings(book) -> None:
    changed = await book.put(
        "/accounts/main",
        json={"name": "Payroll", "type": "savings", "ownership": 0.5, "shared": True},
    )
    assert changed.status_code == 200, changed.text
    main = next(a for a in (await book.get("/state")).json()["accounts"] if a["key"] == "main")
    assert (main["name"], main["type"], main["ownership"], main["shared"]) == (
        "Payroll",
        "savings",
        0.5,
        True,
    )
    assert main["type_label"] == "Savings account"
    bad = await book.put(
        "/accounts/main", json={"name": "X", "type": "nada", "ownership": 1, "shared": False}
    )
    assert bad.status_code == 422
    missing = await book.put(
        "/accounts/nada", json={"name": "X", "type": "current", "ownership": 1, "shared": False}
    )
    assert missing.status_code == 404


async def test_renaming_a_category_keeps_its_history_and_labels(book) -> None:
    state = (await book.get("/state")).json()
    rent = next(c for c in state["categories"] if c["name"] == "Rent")
    await book.put(
        "/label",
        params={"id": "main:m3"},
        json={"parts": [{"amount": "430", "category": rent["id"]}]},
    )
    before = (await book.get("/shared", params={"year": 2026})).json()
    changed = await book.put(
        f"/categories/{rent['id']}",
        json={"name": "Housing", "split": "fifty_fifty", "not_basic": False, "not_living": False},
    )
    assert changed.status_code == 200, changed.text
    after = (await book.get("/shared", params={"year": 2026})).json()
    months = {m["month"]: m for m in after["months"]}
    assert [c["name"] for c in months[2]["by_category"]] == ["Housing"]
    assert "Housing" in {c["name"] for c in months[3]["by_category"]}
    assert after["balance_me"] == pytest.approx(before["balance_me"])
    taken = await book.put(
        f"/categories/{rent['id']}",
        json={"name": "Groceries", "split": "fifty_fifty"},
    )
    assert taken.status_code == 422
    no_split = await book.put(f"/categories/{rent['id']}", json={"name": "Housing"})
    assert no_split.status_code == 422


async def test_a_category_can_be_added_from_settings(book) -> None:
    created = await book.post(
        "/categories",
        json={"nature": "expense", "ownership": "individual", "name": "Travel", "not_basic": True},
    )
    assert created.status_code == 201, created.text
    cats = (await book.get("/state")).json()["categories"]
    trips = next(c for c in cats if c["name"] == "Travel")
    assert trips["not_basic"] and not trips["not_living"] and trips["split"] is None
    again = await book.post(
        "/categories", json={"nature": "expense", "ownership": "individual", "name": "Travel"}
    )
    assert again.status_code == 422


async def test_a_portfolio_photo_moves_with_its_fund_prices_until_the_next(book, schema) -> None:
    plan = "statement:finizens:plan-de-pensiones"
    shot = (date.today() - timedelta(days=3)).isoformat()
    later = (date.today() - timedelta(days=1)).isoformat()
    found = [
        event(
            "finance.account",
            {"bank": "Finizens", "account": plan, "name": "Pension Plan", "kind": "pension"},
            "statement:account:plan",
        ),
        event(
            "finance.balance",
            {"account": plan, "on": shot, "amount": "1000.00", "currency": "EUR"},
            "statement:plan:balance",
        ),
        event(
            "finance.holding",
            {"account": plan, "symbol": "ETF", "on": shot, "value": "900.00"},
            "statement:plan:etf",
        ),
        event(
            "finance.holding",
            {"account": plan, "symbol": "EUR", "on": shot, "value": "100.00", "price": "1"},
            "statement:plan:cash",
        ),
        event(
            "finance.price", {"symbol": "ETF", "on": shot, "price": "50", "currency": "EUR"}, "p1"
        ),
        event(
            "finance.price", {"symbol": "ETF", "on": later, "price": "55", "currency": "EUR"}, "p2"
        ),
    ]
    async with schema.begin() as connection:
        for e in found:
            await connection.execute(
                text("""
                insert into kernel.events (ts, module, source, type, payload, dedup_hash, user_id)
                values (now(), :m, 'statement', :t, cast(:p as jsonb), :d, :u)
            """),
                {
                    "m": e["module"],
                    "t": e["type"],
                    "p": json.dumps(e["payload"]),
                    "d": e["dedup"],
                    "u": PERSON,
                },
            )
    pension = {
        "key": "pension",
        "name": "Pension",
        "institution": "Finizens",
        "type": "pension",
        "movements": "statement",
        "match": {"bank": "Finizens", "key": "Pension Plan"},
    }
    imported = await book.post(
        "/import", json={**BUNDLE, "accounts": [*BUNDLE["accounts"], pension]}
    )
    assert imported.status_code == 200, imported.text

    widget = (await book.get("/widgets/account/value", params={"option": "pension"})).json()
    assert widget["body"]["value"] == 1090.0
    day = date.fromisoformat(later)
    assert widget["body"]["detail"] == f"Pension · estimated at {day.day}/{day.month}"


async def test_the_panel_of_dinero_says_how_you_go_with_the_same_numbers_as_the_summary(
    book,
) -> None:
    found = (await book.get("/panel")).json()
    assert found["area"] == "money"
    assert [tab["id"] for tab in found["tabs"]][:3] == ["summary", "spending", "worth"]
    summary = (await book.get("/summary")).json()
    networth = next(k for k in summary["kpis"] if k["key"] == "networth")
    figure = found["tabs"][0]["blocks"][0]
    assert figure["type"] == "figure" and figure["label"] == "Net worth"
    assert figure["value"].replace(",", "").removeprefix("−").removeprefix("€") == str(
        round(abs(networth["value"]))
    )
    assert {q["text"] for q in found["questions"]} >= {
        "How much do I have?",
        "Do I make it to the end of the month?",
    }
    assert all(q["tab"] in {tab["id"] for tab in found["tabs"]} for q in found["questions"])


async def test_without_accounts_there_is_no_panel(api) -> None:
    assert (await api.get("/panel")).status_code == 404
