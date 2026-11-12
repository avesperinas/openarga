from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from money_people import PERSON
from sqlalchemy import text
from test_money_api import (
    BUNDLE,
    book,  # noqa: F401 -- la fixture con el log y la configuración
    event,
    movement,
)

READ = {"x-arga-scopes": "money:read"}
WRITE = {"x-arga-scopes": "money:write"}
PLAN = "statement:entidad:plan-uno"
SHOT = (date.today() - timedelta(days=3)).isoformat()
LATER = (date.today() - timedelta(days=1)).isoformat()


async def publish(schema, events: list[dict]) -> None:
    async with schema.begin() as connection:
        for e in events:
            await connection.execute(
                text("""
                insert into kernel.events (ts, module, source, type, payload, dedup_hash, user_id)
                values (:ts, :m, 'statement', :t, cast(:p as jsonb), :d, :u)
            """),
                {
                    "ts": e.get("ts", datetime.now(UTC)),
                    "m": e["module"],
                    "t": e["type"],
                    "p": json.dumps(e["payload"]),
                    "d": e["dedup"],
                    "u": PERSON,
                },
            )


def held(symbol: str, value: str, name: str, photo: str | None = None, on: str = SHOT) -> dict:
    payload = {"account": PLAN, "symbol": symbol, "name": name, "on": on, "value": value}
    if photo:
        payload["photo"] = photo
    midnight = datetime.fromisoformat(on).replace(tzinfo=UTC)
    return {**event("finance.holding", payload, f"h:{photo}:{symbol}:{on}"), "ts": midnight}


PLAN_EVENTS = [
    event(
        "finance.account",
        {"bank": "Entidad", "account": PLAN, "name": "Plan Uno", "kind": "roboadvisor"},
        "acc-plan",
    ),
    event(
        "finance.balance",
        {"account": PLAN, "on": SHOT, "amount": "1000.00", "currency": "EUR"},
        "bal-plan",
    ),
]
PLAN_ACCOUNT = {
    "key": "plan",
    "name": "Plan Uno",
    "institution": "Entidad",
    "type": "fund",
    "movements": "statement",
    "match": {"bank": "Entidad", "key": "Plan Uno"},
}


async def with_plan(book, schema, holdings: list[dict]) -> None:  # noqa: F811
    await publish(schema, [*PLAN_EVENTS, *holdings])
    imported = await book.post(
        "/import", json={**BUNDLE, "accounts": [*BUNDLE["accounts"], PLAN_ACCOUNT]}
    )
    assert imported.status_code == 200, imported.text


def period() -> dict:
    today = date.today()
    return {"from": today.replace(day=1).isoformat(), "to": today.isoformat()}


async def test_a_new_photo_of_the_same_day_replaces_the_one_before(book, schema) -> None:  # noqa: F811
    await with_plan(
        book,
        schema,
        [
            held("name:bonos-hedged", "400.00", "Bonos Hedged"),
            held("SPY", "600.00", "SPDR S&P 500 ETF", "a"),
            held("name:otros-bonos", "400.00", "Otros Bonos", "a"),
        ],
    )
    await publish(
        schema,
        [
            held("SPY", "600.00", "SPDR S&P 500 ETF", "b"),
            held("0P0001I704.F", "400.00", "iShares Emerging Gov Bond Index", "b"),
        ],
    )
    product = (await book.get("/products/plan")).json()
    funds = {f["symbol"]: f for f in product["photo"]["funds"]}
    assert set(funds) == {"SPY", "0P0001I704.F"}
    assert sum(f["value"] for f in funds.values()) == 1000.0
    assert funds["SPY"]["asset"] == "equity" and funds["SPY"]["regions"][0]["key"] == "us"
    assert product["value_how"].startswith("La última foto")
    assert product["source"]["name"] == "Plan Uno"


async def test_a_corrected_photo_of_the_same_day_brings_its_value_too(book, schema) -> None:  # noqa: F811
    await with_plan(
        book,
        schema,
        [held("SPY", "900.00", "SPDR S&P 500 ETF", "a"), held("EUR", "100.00", "Liquidez", "a")],
    )
    await publish(
        schema,
        [
            event(
                "finance.balance",
                {"account": PLAN, "on": SHOT, "amount": "1050.00", "currency": "EUR"},
                "bal-plan-corrected",
            ),
            held("SPY", "1000.00", "SPDR S&P 500 ETF", "b"),
            held("EUR", "50.00", "Liquidez", "b"),
        ],
    )
    product = (await book.get("/products/plan")).json()
    assert product["value"] == 1050.0
    funds = {f["symbol"]: f["value"] for f in product["photo"]["funds"]}
    assert funds == {"SPY": 1000.0, "EUR": 50.0}


async def test_photos_without_an_id_still_add_up_fund_by_fund(book, schema) -> None:  # noqa: F811
    await with_plan(
        book,
        schema,
        [held("SPY", "600.00", "SPDR S&P 500 ETF"), held("EUR", "400.00", "Liquidez")],
    )
    funds = (await book.get("/products/plan")).json()["photo"]["funds"]
    assert {f["symbol"] for f in funds} == {"SPY", "EUR"}


async def test_the_composition_by_asset_region_and_fund_and_what_cannot_be_split(
    book,  # noqa: F811
    schema,
) -> None:
    await with_plan(
        book,
        schema,
        [
            held("SPY", "500.00", "SPDR S&P 500 ETF", "a"),
            held("VPL", "200.00", "Vanguard FTSE Pacific ETF", "a"),
            held("name:raro", "200.00", "Fondo Raro", "a"),
            held("EUR", "100.00", "Liquidez", "a"),
        ],
    )
    comp = (await book.get("/analysis/composition", params=period())).json()
    assets = {r["key"]: r["value"] for r in comp["by_asset"]}
    assert assets == {"equity": 700.0, "unknown": 200.0, "cash": 100.0}
    regions = {r["key"]: r["value"] for r in comp["by_region"]}
    assert regions["us"] == 500.0 and regions["japan"] == 116.0 and regions["pacific"] == 84.0
    assert regions["cash"] == 100.0 and regions["unknown"] == 200.0
    assert comp["unknown_asset"] == 200.0 and comp["total"] == 1000.0
    assert [f["key"] for f in comp["by_fund"]][0] == "SPY"

    put = await book.put(
        "/funds/name:raro", json={"asset": "bond", "regions": {"europe": 50, "emerging": 50}}
    )
    assert put.status_code == 200, put.text
    comp = (await book.get("/analysis/composition", params=period())).json()
    assert {r["key"]: r["value"] for r in comp["by_asset"]}["bond"] == 200.0
    assert comp["unknown_region"] == 0.0
    bad = await book.put("/funds/name:raro", json={"asset": "bond", "regions": {"europe": 70}})
    assert bad.status_code == 422


async def test_each_fund_moves_with_its_price_and_the_funds_add_up_to_the_product(
    book,  # noqa: F811
    schema,
) -> None:
    await with_plan(
        book,
        schema,
        [
            held("SPY", "500.00", "SPDR S&P 500 ETF", "a"),
            held("EUR", "500.00", "Liquidez", "a"),
            event("finance.price", {"symbol": "SPY", "on": SHOT, "price": "100"}, "p1"),
            event("finance.price", {"symbol": "SPY", "on": LATER, "price": "110"}, "p2"),
        ],
    )
    product = (await book.get("/products/plan")).json()
    assert product["value"] == 1050.0
    funds = {f["symbol"]: f for f in product["photo"]["funds"]}
    assert funds["SPY"]["value"] == 550.0 and funds["SPY"]["change"] == 0.1
    assert funds["EUR"]["value"] == 500.0 and funds["EUR"]["change"] is None


async def test_an_etf_valued_by_its_isin_moves_with_the_price_of_its_line(
    book,  # noqa: F811
    schema,
) -> None:
    line = {"isin": "IE000W8WMSL2", "kind": "listed", "mic": "XETR", "quote_currency": "EUR"}
    symbol = "IE000W8WMSL2:XETR:EUR"
    etf = held(symbol, "900.00", "WISDOMTREE QUANTUM COMP ETF", "a")
    etf["payload"].update(line, quantity="30", price="30")
    await with_plan(
        book,
        schema,
        [
            etf,
            held("EUR", "100.00", "Liquidez", "a"),
            event("finance.price", {"symbol": symbol, "on": SHOT, "price": "30", **line}, "p1"),
            event("finance.price", {"symbol": symbol, "on": LATER, "price": "33", **line}, "p2"),
        ],
    )
    product = (await book.get("/products/plan")).json()
    assert product["value"] == 1090.0
    funds = {f["symbol"]: f for f in product["photo"]["funds"]}
    assert funds[symbol]["value"] == 990.0 and funds[symbol]["change"] == 0.1
    assert (funds[symbol]["asset"], funds[symbol]["classified"]) == ("equity", "catalog")


async def test_a_product_is_created_changed_and_given_its_ibans(book) -> None:  # noqa: F811
    created = await book.post(
        "/accounts",
        json={"name": "Fianza del piso", "type": "deposit", "institution": "Una inmobiliaria"},
    )
    assert created.status_code == 201, created.text
    product = created.json()
    assert product["key"] == "fianza_del_piso" and product["group"] == "Fianzas"
    assert product["movements"] == "matched"
    assert "Es dinero tuyo fuera que vuelve: ni ahorro ni gasto" in product["traits"]

    again = await book.post(
        "/accounts", json={"name": "Fianza del piso", "type": "deposit", "institution": "Otra"}
    )
    assert again.json()["key"] == "fianza_del_piso_2"

    changed = await book.patch(
        "/accounts/fianza_del_piso",
        json={"name": "Fianza del local", "ibans": ["es00 0000 0000 0000 0000 9999"]},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["name"] == "Fianza del local"
    assert changed.json()["ibans"] == ["ES0000000000000000009999"]
    assert changed.json()["institution"] == "Una inmobiliaria"
    bad = await book.patch("/accounts/fianza_del_piso", json={"ibans": ["no es un iban"]})
    assert bad.status_code == 422
    wrong = await book.post(
        "/accounts", json={"name": "X", "type": "no-existe", "institution": "Y"}
    )
    assert wrong.status_code == 422

    valued = await book.put(
        "/accounts/fianza_del_piso/value", json={"on": date.today().isoformat(), "value": "900"}
    )
    assert valued.json()["value"] == 900.0 and valued.json()["value_how"]


async def test_an_unassigned_source_account_becomes_a_product(book, schema) -> None:  # noqa: F811
    await publish(
        schema,
        [
            event(
                "finance.account",
                {
                    "account": "src-new",
                    "bank": "Banco Uno",
                    "name": "TITULAR UNO",
                    "kind": "savings",
                    "iban_tail": "3333",
                    "iban": "ES0000000000000000003333",
                },
                "acc-new",
            ),
            *movement("src-new", "n1", "2026-03-20", "50.00", "INTERESES"),
        ],
    )
    state = (await book.get("/state")).json()
    assert [u["key"] for u in state["unmapped"]] == ["src-new"]
    created = await book.post(
        "/accounts",
        json={"name": "Ahorro", "type": "savings", "institution": "BBVA", "source": "src-new"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["movements"] == "api"
    assert created.json()["source"]["iban_tail"] == "3333"
    state = (await book.get("/state")).json()
    assert state["unmapped"] == []
    twice = await book.post(
        "/accounts",
        json={"name": "Otra", "type": "savings", "institution": "BBVA", "source": "src-new"},
    )
    assert twice.status_code == 422


async def test_what_bitvavo_brings_is_the_value_of_its_product(book, schema) -> None:  # noqa: F811
    from hub.providers import bitvavo

    day = date.today()
    brought = [
        bitvavo.account_event(day),
        *bitvavo.events(
            {"BTC": Decimal("0.5"), "EUR": Decimal("100")}, {"BTC": Decimal("40000")}, day
        ),
    ]
    await publish(
        schema,
        [
            {
                **event(e["type"], e["payload"], e["dedup_hash"]),
                "ts": datetime.fromisoformat(e["ts"]),
            }
            for e in brought
        ],
    )
    state = (await book.get("/state")).json()
    assert [u["key"] for u in state["unmapped"]] == ["bitvavo"]

    created = await book.post(
        "/accounts", json={"name": "Cripto", "type": "crypto", "institution": "Bitvavo"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["value"] is None
    assigned = await book.patch(f"/accounts/{created.json()['key']}", json={"source": "bitvavo"})
    assert assigned.status_code == 200, assigned.text
    product = assigned.json()
    assert product["source"]["bank"] == "Bitvavo"
    assert (product["value"], product["value_since"]) == (20100.0, day.isoformat())


async def test_a_typed_composition_wins_over_the_source_and_sets_the_value(
    book,  # noqa: F811
    schema,
) -> None:
    await with_plan(book, schema, [held("SPY", "1000.00", "SPDR S&P 500 ETF", "a")])
    typed = await book.put(
        "/accounts/plan/composition",
        json={
            "on": SHOT,
            "total": "1200",
            "funds": [
                {"name": "SPDR S&P 500", "weight": "50"},
                {"name": "Vanguard Global Short Bond Index Hedged Inst Plus", "weight": "50"},
            ],
        },
    )
    assert typed.status_code == 200, typed.text
    photo = typed.json()["photo"]
    assert photo["typed"]
    assert {f["symbol"] for f in photo["funds"]} == {"SPY", "0P00012NJE.F"}
    assert sum(f["value"] for f in photo["funds"]) == 1000.0
    wrong = await book.put(
        "/accounts/plan/composition",
        json={"on": SHOT, "total": "1200", "funds": [{"name": "SPY", "value": "100"}]},
    )
    assert wrong.status_code == 422 and "suman" in wrong.json()["detail"]
    removed = await book.delete("/accounts/plan/composition", params={"on": SHOT})
    assert not removed.json()["photo"]["typed"]
    exported = (await book.get("/export")).json()
    assert exported["holdings"] == []


async def test_a_rule_is_shown_and_removed_keeping_what_it_explained(book, schema) -> None:  # noqa: F811
    await publish(
        schema,
        movement("src-main", "f1", "2026-03-20", "-900.00", "FIANZA INVENTADA PISO"),
    )
    deposit = {
        "key": "deposit",
        "name": "Fianza",
        "institution": "Una inmobiliaria",
        "type": "deposit",
        "movements": "matched",
    }
    imported = await book.post(
        "/import",
        json={
            **BUNDLE,
            "accounts": [*BUNDLE["accounts"], deposit],
            "rules": [{"text": "FIANZA INVENTADA", "transfer_to": "deposit"}, *BUNDLE["rules"]],
        },
    )
    assert imported.status_code == 200, imported.text
    rules = (await book.get("/rules")).json()
    first = rules[0]
    assert first["then"] == "Traspaso con Fianza" and first["movements"] == 1
    assert "deposit" in first["accounts"]
    assert (await book.get("/products/deposit")).json()["rules"][0]["id"] == first["id"]

    removed = await book.delete(f"/rules/{first['id']}")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"kept": 1}
    assert first["id"] not in {r["id"] for r in (await book.get("/rules")).json()}
    fact = (await book.get("/movement", params={"id": "main:f1"})).json()
    assert fact["status"] == "transfer"
    assert (await book.get("/products/deposit")).json()["value"] == 900.0


async def test_the_product_tools_read_and_write_with_their_roles(book, schema) -> None:  # noqa: F811
    await with_plan(
        book,
        schema,
        [held("SPY", "600.00", "SPDR S&P 500 ETF", "a"), held("EUR", "400.00", "Liquidez", "a")],
    )
    listed = (await book.post("/tools/get_products", json={}, headers=READ)).json()["content"]
    assert "plan" in {p["key"] for p in listed["products"]}
    one = await book.post("/tools/get_products", json={"product": "plan uno"}, headers=READ)
    assert one.json()["content"]["photo"]["funds"][0]["symbol"] == "SPY"
    comp = (await book.post("/tools/get_composition", json={}, headers=READ)).json()["content"]
    assert {r["key"] for r in comp["by_asset"]} >= {"equity", "cash"}

    refused = await book.post(
        "/tools/create_product",
        json={"name": "Cripto", "type": "crypto", "institution": "Exchange"},
        headers=READ,
    )
    assert refused.status_code == 403
    created = await book.post(
        "/tools/create_product",
        json={"name": "Cripto", "type": "crypto", "institution": "Exchange", "ownership": 100},
        headers=WRITE,
    )
    assert created.json()["content"]["created"] == "cripto"
    renamed = await book.post(
        "/tools/update_product",
        json={"product": "Plan Uno", "name": "Plan Global", "ownership": 50},
        headers=WRITE,
    )
    assert renamed.json()["content"] == {"updated": "plan"}
    recorded = await book.post(
        "/tools/record_composition",
        json={
            "product": "Plan Global",
            "on": SHOT,
            "funds": [
                {"name": "SPDR S&P 500 ETF", "value": "500"},
                {"name": "Fondo Nuevo", "value": "500"},
            ],
        },
        headers=WRITE,
    )
    assert recorded.json()["content"]["unclassified"] == ["Fondo Nuevo"]
    classified = await book.post(
        "/tools/classify_fund",
        json={"fund": "Fondo Nuevo", "asset": "bond", "regions": {"europe": 100}},
        headers=WRITE,
    )
    assert classified.json()["content"]["fund"] == "name:fondo-nuevo"
    comp = (await book.post("/tools/get_composition", json={}, headers=READ)).json()["content"]
    assert {r["key"]: r["value"] for r in comp["by_region"]}["europe"] == 250.0
    rules = (await book.post("/tools/get_rules", json={}, headers=READ)).json()["content"]
    assert rules["rules"] and all("when" in r for r in rules["rules"])
    gone = await book.post(
        "/tools/delete_rule", json={"rule_id": rules["rules"][0]["id"]}, headers=WRITE
    )
    assert gone.json()["content"]["deleted"] == rules["rules"][0]["id"]
