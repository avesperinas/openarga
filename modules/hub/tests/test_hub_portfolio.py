from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import capabilities, statements
from hub.funds import catalogue, symbol_of
from hub.tools import TOOLS


def p(*texts: str) -> str:
    return "".join(f"<p>{one}</p>" for one in texts)


def header(name: str, day: str, total: str, given: str) -> str:
    return (
        "<html><head><title>Finizens</title></head><body>"
        f"{p('Producto seleccionado', name, '6 - Agresivo', 'Tu cartera', 'Movimientos')}"
        f"{p('Plan de Inversión - 1', '9,99 €', 'Aportado neto', 'Aportado', '9,99 €')}"
        f"{p('Total', 'Total de tu cartera', 'Rent. €', 'Histórico acumulado', f'A {day}')}"
        f"{p('Total', 'Total de tu cartera', f'{total} €', 'Aportado neto', f'{given} €')}"
        f"{p('Rentabilidad', '+1,00 €', 'Composición de la Cartera', 'Renta variable', '99,00%')}"
    )


def investment_page(rows: list[tuple[str, str, str, str]], total: str = "1.000,00") -> str:
    table = "".join(
        p(name, value, "+1,00%", "(1,00 €)", "50,00%", "50,00%", "(0,00%)", units, f"{nav} €")
        for name, value, units, nav in rows
    )
    return (
        header("Plan de Inversión - 1", "05/10/2030", total, "900,00")
        + p("Fondos", "Ocultar detalle", "Fondo", "Valor", "Rendimiento", "Distribución")
        + p("Objetivo", "Participaciones", "V. Liqd.")
        + table
        + p("Los Folletos Explicativos de los Fondos", "Fondos", "Ver detalle")
        + "</body></html>"
    )


INVESTMENT = [
    ("Vanguard US 500 Index Inst Plus", "600,00", "1,00", "600,00"),
    ("Vanguard European Index Inst Plus", "390,00", "1,30", "300,00"),
    ("Liquidez", "10,00", "10,00", "1,00"),
]


def pension_page(weights: list[tuple[str, str]]) -> str:
    listed = "".join(p(name, weight) for name, weight in weights)
    return (
        header("Plan de Pensiones", "04/10/2030", "2.000,00", "1.950,00")
        + p("Participaciones", "190,0000", "Valor liquidativo", "10,5263 €")
        + p("Fondos", "Ocultar detalle", "Fondo", "Distribución")
        + listed
        + p("Los Folletos Explicativos de los Fondos", "Fondos", "Ver detalle")
        + "</body></html>"
    )


def test_every_fund_of_the_catalogue_has_one_symbol() -> None:
    funds = catalogue()
    assert len({fund.name for fund in funds}) == len(funds)
    assert all(fund.currency in ("EUR", "USD") for fund in funds)
    assert symbol_of("  vanguard us 500 index INST plus ") == "0P00011HBK.F"
    assert symbol_of("Liquidez") == "EUR"
    assert symbol_of("Un fondo que nadie conoce") is None


def test_an_investment_plan_reads_each_fund_with_its_units_and_price() -> None:
    read = statements.read(investment_page(INVESTMENT), date(2030, 10, 6))

    (balance,) = read.balances
    assert balance.on == date(2030, 10, 5)
    assert (balance.amount, balance.contributed) == (Decimal("1000.00"), Decimal("900.00"))
    by = {h.symbol: h for h in read.holdings}
    us = by["0P00011HBK.F"]
    assert (us.value, us.quantity, us.price) == (
        Decimal("600.00"),
        Decimal("1.00"),
        Decimal("600.00"),
    )
    assert (by["EUR"].value, by["EUR"].price) == (Decimal("10.00"), Decimal(1))
    assert {h.account for h in read.holdings} == {"statement:finizens:plan-de-inversion-1"}
    assert read.skipped == []


def test_a_pension_plan_gives_weights_and_each_fund_is_its_share_of_the_total() -> None:
    read = statements.read(
        pension_page(
            [
                ("SPDR S&P 500 ETF", "60,00%"),
                ("Amundi Core Stoxx Europe 600 ETF", "39,00%"),
                ("Liquidez", "1,00%"),
            ]
        ),
        date(2030, 10, 6),
    )

    by = {h.symbol: h for h in read.holdings}
    assert by["SPY"].value == Decimal("1200.00") and by["SPY"].quantity is None
    assert by["MEUD.PA"].value == Decimal("780.00")
    assert by["EUR"].value == Decimal("20.00")
    assert read.balances[0].on == date(2030, 10, 4)


def test_funds_that_do_not_add_up_to_the_plan_publish_nothing() -> None:
    with pytest.raises(statements.StatementError, match="suman"):
        statements.read(investment_page(INVESTMENT, total="2.000,00"), date(2030, 10, 6))


def test_a_fund_without_a_price_still_counts_and_says_so() -> None:
    rows = [*INVESTMENT[:2], ("Fondo Inventado Index", "10,00", "1,00", "10,00")]
    read = statements.read(investment_page(rows), date(2030, 10, 6))
    assert "name:fondo-inventado-index" in {h.symbol for h in read.holdings}
    assert any("Fondo Inventado Index" in why for why in read.skipped)


def test_the_holdings_go_out_as_finance_holding_with_their_identity() -> None:
    read = statements.read(investment_page(INVESTMENT), date(2030, 10, 6))
    out = [e for e in statements.events_of(read) if e["type"] == "finance.holding"]
    assert len(out) == 3
    us = next(e for e in out if e["payload"]["symbol"] == "0P00011HBK.F")
    photo = us["payload"].pop("photo")
    assert {e["payload"].get("photo", photo) for e in out} == {photo}
    assert us["payload"] == {
        "account": "statement:finizens:plan-de-inversion-1",
        "symbol": "0P00011HBK.F",
        "name": "Vanguard US 500 Index Inst Plus",
        "on": "2030-10-05",
        "value": "600.00",
        "quantity": "1.00",
        "price": "600.00",
    }
    assert len({e["dedup_hash"] for e in out}) == 3


def test_the_same_photo_twice_is_the_same_and_a_different_one_is_new() -> None:
    first = statements.events_of(statements.read(investment_page(INVESTMENT), date(2030, 10, 6)))
    again = statements.events_of(statements.read(investment_page(INVESTMENT), date(2030, 10, 6)))
    held = lambda events: [e for e in events if e["type"] == "finance.holding"]  # noqa: E731
    assert {e["dedup_hash"] for e in held(first)} == {e["dedup_hash"] for e in held(again)}

    moved = [(INVESTMENT[0][0], "620,00", "1,00", "620,00"), *INVESTMENT[1:]]
    other = held(
        statements.events_of(
            statements.read(investment_page(moved, total="1.020,00"), date(2030, 10, 6))
        )
    )
    assert {e["payload"]["photo"] for e in other}.isdisjoint(
        {e["payload"]["photo"] for e in held(first)}
    )
    assert not {e["dedup_hash"] for e in other} & {e["dedup_hash"] for e in held(first)}


def test_two_spellings_of_the_same_fund_are_one_fund() -> None:
    assert symbol_of("Vanguard Global Short Bond Index Hedged Inst Plus") == "0P00012NJE.F"
    assert symbol_of("iShares Developed Real Estate Index Fund") == "0P0000Y354.F"
    with pytest.raises(statements.StatementError, match="dos veces"):
        statements.portfolio(
            "Finizens",
            "Plan de Inversión - 1",
            date(2030, 10, 6),
            Decimal("200"),
            None,
            [
                statements.Shown("iShares Developed Real Estate Index", value=Decimal("100")),
                statements.Shown("iShares Developed Real Estate Index Fund", value=Decimal("100")),
            ],
        )


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, monkeypatch):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    monkeypatch.setattr(capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    clean = text("delete from kernel.events where module = 'hub'")
    async with kernel_db.engine().begin() as connection:
        await connection.execute(clean)
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(clean)
    await kernel_db.engine().dispose()


async def published(schema) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select type, payload from kernel.events "
                    "where module = 'hub' order by type, dedup_hash"
                )
            )
        ).all()


SHOT = {
    "entity": "Finizens",
    "product": "Plan de Pensiones",
    "on": "2030-10-04",
    "value": "2000",
    "contributed": "1950",
    "funds": [
        {"name": "SPDR S&P 500 ETF", "weight": "60"},
        {"name": "Amundi Core Stoxx Europe 600 ETF", "weight": "39"},
        {"name": "Liquidez", "weight": "1"},
    ],
}


async def test_a_screenshot_told_by_the_model_is_published_like_the_page(
    api, kernel, schema
) -> None:
    first = await api.post(
        "/tools/record_portfolio", json=SHOT, headers={"x-arga-scopes": "hub:write"}
    )
    again = await api.post(
        "/tools/record_portfolio", json=SHOT, headers={"x-arga-scopes": "hub:write"}
    )

    assert first.status_code == 200, first.text
    said = first.json()["content"]
    assert said["recorded"] and said["funds"] == 3 and said["new"] == 5
    assert again.json()["content"]["new"] == 0
    rows = await published(schema)
    holdings = {r.payload["symbol"]: r.payload for r in rows if r.type == "finance.holding"}
    assert holdings["SPY"]["value"] == "1200.00"
    balance = next(r.payload for r in rows if r.type == "finance.balance")
    assert balance["account"] == "statement:finizens:plan-de-pensiones"
    assert balance["amount"] == "2000"


async def test_a_screenshot_that_does_not_add_up_is_not_recorded(api, kernel, schema) -> None:
    wrong = {**SHOT, "funds": [{"name": "SPDR S&P 500 ETF", "weight": "50"}]}
    response = await api.post(
        "/tools/record_portfolio", json=wrong, headers={"x-arga-scopes": "hub:write"}
    )
    assert response.json()["content"]["recorded"] is False
    assert await published(schema) == []


def test_the_tool_is_declared_in_the_manifest_with_write_scope() -> None:
    from pathlib import Path

    import yaml

    manifest = yaml.safe_load((Path(__file__).resolve().parents[1] / "manifest.yaml").read_text())
    tools = {tool["name"]: tool["scope"] for tool in manifest["tools"]}
    assert tools["record_portfolio"] == "hub:write"
    assert set(tools) == set(TOOLS)
