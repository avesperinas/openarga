from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from markets_fake import QUANTUM, SP500, Markets, markets
from sqlalchemy import text

from arga_contracts import sources
from hub import capabilities, connections, instruments, sync
from hub.funds import Fund
from hub.instruments import Line, Unresolved
from hub.providers import prices

PHOTO = date(2030, 10, 29)
D = [PHOTO - timedelta(days=2), PHOTO - timedelta(days=1), PHOTO, PHOTO + timedelta(days=1)]
TODAY = D[-1]
XETRA = f"{QUANTUM}:XETR:EUR"


async def resolve(found: Markets, **asked) -> Line:
    async with httpx.AsyncClient(transport=httpx.MockTransport(found)) as client:
        return await instruments.resolve(client, since=PHOTO, **asked)


async def test_the_myinvestor_name_gives_its_isin_and_its_xetra_line_in_euros() -> None:
    line = await resolve(markets(), name="WISDOMTREE QUANTUM COMP ETF")

    assert (line.isin, line.kind, line.mic, line.currency) == (QUANTUM, "listed", "XETR", "EUR")
    assert line.symbol == XETRA
    assert line.yahoo == "WQTM.DE"
    assert (line.onvista_entity, line.onvista_notation) == ("FUND/298266867", 1)
    assert Line.from_stored(line.stored()) == line


async def test_another_line_is_chosen_by_saying_it() -> None:
    london = await resolve(markets(), name="x", isin=QUANTUM, mic="XLON", currency="USD")
    assert (london.symbol, london.yahoo, london.onvista_notation) == (
        f"{QUANTUM}:XLON:USD",
        "WQTM.L",
        3,
    )
    pence = await resolve(markets(), name="x", isin=QUANTUM, mic="XLON", currency="GBp")
    assert pence.symbol == f"{QUANTUM}:XLON:GBP"

    with pytest.raises(Unresolved, match="no cotiza en XPAR"):
        await resolve(markets(), name="x", isin=QUANTUM, mic="XPAR")


async def test_a_mistyped_isin_or_an_unknown_name_asks_for_the_isin() -> None:
    with pytest.raises(Unresolved, match="no es un ISIN"):
        await resolve(markets(), name="x", isin="IE000W8WMSL3")
    with pytest.raises(Unresolved, match="dime su ISIN"):
        await resolve(markets(), name="Un ETF que nadie conoce")


async def test_a_fund_is_valued_by_its_nav_and_has_no_line() -> None:
    found = markets()
    found.instruments["IE00BFPM9V94"] = SimpleNamespace(
        isin="IE00BFPM9V94",
        name="Vanguard U.S. 500 Stock Index Fund",
        entity="FUND/68002011",
        subtype="FUND",
        venues=[SimpleNamespace(code="@_WM", currency="EUR", notation=21, money=0.0)],
    )
    found.yahoo_search["IE00BFPM9V94"] = ["0P00011HBK.F"]

    line = await resolve(found, name="x", isin="IE00BFPM9V94")

    assert (line.kind, line.mic, line.symbol) == ("fund", None, "IE00BFPM9V94")
    assert (line.yahoo, line.onvista_notation) == ("0P00011HBK.F", 21)


async def test_without_onvista_openfigi_still_finds_the_xetra_line() -> None:
    found = markets()
    found.down.add("api.onvista.de")

    line = await resolve(found, name="x", isin=QUANTUM)

    assert (line.symbol, line.yahoo, line.onvista_entity) == (XETRA, "WQTM.DE", None)


def target(*lines: Line, filled: dict | None = None) -> SimpleNamespace:
    config = {"instruments": [line.stored() for line in lines]}
    if filled is not None:
        config["filled"] = filled
    return SimpleNamespace(config=config)


@pytest.fixture
def vanguard(monkeypatch):
    fund = Fund("Vanguard US 500 Index Inst Plus", "0P00011HBK.F", "EUR", "IE00BFPM9V94")
    monkeypatch.setattr(prices, "catalogue", lambda: (fund,))
    return fund


async def run(found: Markets, connection) -> prices.Fetched:
    async with httpx.AsyncClient(transport=httpx.MockTransport(found)) as client:
        return await prices.fetch(
            client,
            instruments.stored(connection.config),
            connection.config.get("filled"),
            today=TODAY,
        )


def by_day(got, symbol: str) -> dict[str, str]:
    return {
        e["payload"]["on"]: e["payload"]["price"]
        for e in got.events
        if e["payload"]["symbol"] == symbol
    }


async def test_the_xetra_line_is_priced_from_its_photo_and_onvista_fills_what_yahoo_misses(
    vanguard,
) -> None:
    found = markets()
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0), (D[1], 606.0)])
    found.yahoo["WQTM.DE"] = ("EUR", [(D[0], 28.5), (D[1], None), (D[2], 30.0)])
    found.eod[1] = ("EUR", [(D[0], 28.5), (D[1], 28.985), (D[2], 30.0)])
    line = await resolve(found, name="WISDOMTREE QUANTUM COMP ETF")

    got = await run(found, target(line))

    assert got.problem is None
    assert by_day(got, XETRA) == {
        D[0].isoformat(): "28.500000",
        D[1].isoformat(): "28.985000",
        D[2].isoformat(): "30.000000",
    }
    one = next(e for e in got.events if e["payload"]["symbol"] == XETRA)
    assert {
        k: one["payload"][k] for k in ("isin", "mic", "kind", "quote_currency", "currency")
    } == {
        "isin": QUANTUM,
        "mic": "XETR",
        "kind": "listed",
        "quote_currency": "EUR",
        "currency": "EUR",
    }
    for event in got.events:
        sources.check(event["type"], event["payload"])
    asked = next(r for r in found.asked if r.url.path.endswith("/WQTM.DE"))
    assert int(asked.url.params["period1"]) <= int(
        prices.datetime.combine(PHOTO, prices.datetime.min.time(), prices.UTC).timestamp()
    )
    assert got.state == {"filled": {XETRA: PHOTO.isoformat()}}


async def test_a_filled_line_is_asked_only_for_the_last_months(vanguard) -> None:
    found = markets()
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0)])
    found.yahoo["WQTM.DE"] = ("EUR", [(D[0], 28.5)])
    line = Line(QUANTUM, "listed", "WQTM", "EUR", PHOTO - timedelta(days=400), "XETR", "WQTM.DE")

    await run(found, target(line, filled={XETRA: line.since.isoformat()}))

    asked = next(r for r in found.asked if r.url.path.endswith("/WQTM.DE"))
    start = prices.datetime.fromtimestamp(int(asked.url.params["period1"]), prices.UTC).date()
    assert start == TODAY - prices.RECENT


async def test_a_dollar_etf_goes_out_in_euros_with_the_ecb_rate_of_its_day(vanguard) -> None:
    found = markets()
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0)])
    found.yahoo["CSPX.L"] = ("USD", [(D[0], 110.0), (D[1], 121.0)])
    found.fx["USD"] = [(D[0], 1.1), (D[1], 1.21)]
    line = await resolve(found, name="x", isin=SP500, mic="XLON", currency="USD")

    got = await run(found, target(line))

    assert line.symbol == f"{SP500}:XLON:USD"
    assert by_day(got, line.symbol) == {
        D[0].isoformat(): "100.000000",
        D[1].isoformat(): "100.000000",
    }
    assert not any(r.url.path.endswith("EURUSD=X") for r in found.asked)


async def test_a_line_in_pence_is_priced_in_pounds_then_euros(vanguard) -> None:
    found = markets()
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0)])
    found.yahoo["WQTM.L"] = ("GBp", [(D[0], 2500.0)])
    found.fx["GBP"] = [(D[0], 0.8)]
    line = Line(QUANTUM, "listed", "WQTM", "GBp", PHOTO, "XLON", "WQTM.L")

    got = await run(found, target(line))

    assert by_day(got, f"{QUANTUM}:XLON:GBP") == {D[0].isoformat(): "31.250000"}


async def test_when_yahoo_is_down_onvista_prices_the_line(vanguard) -> None:
    found = markets()
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0)])
    found.eod[1] = ("EUR", [(D[0], 28.5), (D[1], 29.0)])
    line = await resolve(found, name="WISDOMTREE QUANTUM COMP ETF")
    found.yahoo.pop("WQTM.DE", None)

    got = await run(found, target(line))

    assert got.problem is None
    assert by_day(got, XETRA) == {D[0].isoformat(): "28.500000", D[1].isoformat(): "29.000000"}


async def test_the_funds_that_already_worked_go_out_as_before(vanguard) -> None:
    found = markets()
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0), (D[1], 606.0)])

    got = await run(found, target())

    assert [e["payload"] for e in got.events] == [
        {
            "symbol": "0P00011HBK.F",
            "on": D[0].isoformat(),
            "price": "600.000000",
            "currency": "EUR",
            "name": "Vanguard US 500 Index Inst Plus",
        },
        {
            "symbol": "0P00011HBK.F",
            "on": D[1].isoformat(),
            "price": "606.000000",
            "currency": "EUR",
            "name": "Vanguard US 500 Index Inst Plus",
        },
    ]
    assert got.events[0]["dedup_hash"] == f"prices:0P00011HBK.F:{D[0].isoformat()}:600.000000"
    assert (got.problem, got.state) == (None, None)


async def test_a_line_without_price_does_not_stop_the_funds_but_is_said(vanguard) -> None:
    found = markets()
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0)])
    line = await resolve(found, name="WISDOMTREE QUANTUM COMP ETF")

    got = await run(found, target(line))

    assert by_day(got, "0P00011HBK.F") == {D[0].isoformat(): "600.000000"}
    assert by_day(got, XETRA) == {}
    assert QUANTUM in got.problem and "Xetra" in got.problem
    assert got.state == {"filled": {}}


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


async def events_of(schema, kind: str) -> list[dict]:
    async with schema.connect() as connection:
        return [
            row.payload
            for row in await connection.execute(
                text(
                    "select payload from kernel.events where module = 'hub' "
                    "and type = :type order by dedup_hash"
                ),
                {"type": kind},
            )
        ]


async def config_of(schema, connection_id: UUID) -> dict:
    async with schema.connect() as connection:
        return await connection.scalar(
            text("select config from hub.hub_connection where id = :id"),
            {"id": connection_id},
        )


SHOT = {
    "entity": "MyInvestor",
    "product": "Cartera de ETFs",
    "on": PHOTO.isoformat(),
    "value": "1000",
    "funds": [
        {"name": "WISDOMTREE QUANTUM COMP ETF", "value": "990", "quantity": "33", "price": "30"},
        {"name": "Liquidez", "value": "10"},
    ],
}


async def test_the_myinvestor_etf_is_recorded_with_its_line_priced_and_its_failures_seen(
    api, kernel, schema, monkeypatch, vanguard
) -> None:
    found = markets()
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(found))
    created = await api.post("/connections", json={"provider": "prices", "label": "Precios"})
    assert created.status_code == 201, created.text
    connection_id = UUID(created.json()["id"])

    recorded = await api.post(
        "/tools/record_portfolio", json=SHOT, headers={"x-arga-scopes": "hub:write"}
    )

    said = recorded.json()["content"]
    assert said["recorded"], said
    assert said["without_price"] == []
    assert said["priced_by_isin"] == [
        f"«WISDOMTREE QUANTUM COMP ETF»: {QUANTUM} (cotizado, Xetra, EUR), con precio desde el "
        f"{PHOTO:%d/%m/%Y}"
    ]
    held = {h["symbol"]: h for h in await events_of(schema, "finance.holding")}
    assert set(held) == {XETRA, "EUR"}
    assert {k: held[XETRA][k] for k in ("isin", "kind", "mic", "quote_currency", "value")} == {
        "isin": QUANTUM,
        "kind": "listed",
        "mic": "XETR",
        "quote_currency": "EUR",
        "value": "990",
    }
    stored = await config_of(schema, connection_id)
    assert [one["isin"] for one in stored["instruments"]] == [QUANTUM]

    row = SimpleNamespace(id=connection_id, provider="prices", label="Precios", config=stored)
    found.yahoo["0P00011HBK.F"] = ("EUR", [(D[0], 600.0)])

    async def no_wait(_: float) -> None:
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(found)) as source:
        for _ in range(connections.FAILURES):
            await sync.run(row, source=source, kernel=kernel, sleep=no_wait, attempts=1)
        async with schema.connect() as connection:
            (listed,) = await connections.listed(connection)
        assert listed.state == "failing"
        assert QUANTUM in listed.reason and "Xetra" in listed.reason

        found.yahoo["WQTM.DE"] = ("EUR", [(D[1], 29.0), (D[2], 30.0), (D[3], 31.5)])
        ok = await sync.run(row, source=source, kernel=kernel, sleep=no_wait, attempts=1)
    assert ok.outcome == "ok", ok.detail
    priced = {
        p["on"]: Decimal(p["price"])
        for p in await events_of(schema, "finance.price")
        if p["symbol"] == XETRA
    }
    assert priced == {
        D[1].isoformat(): Decimal("29"),
        D[2].isoformat(): Decimal("30"),
        D[3].isoformat(): Decimal("31.5"),
    }
    assert (await config_of(schema, connection_id))["filled"] == {XETRA: PHOTO.isoformat()}


async def test_without_a_prices_connection_the_tool_says_how_to_value_it(
    api, kernel, schema, monkeypatch
) -> None:
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(markets()))

    recorded = await api.post(
        "/tools/record_portfolio", json=SHOT, headers={"x-arga-scopes": "hub:write"}
    )

    said = recorded.json()["content"]
    assert said["recorded"]
    assert any("conecta «Precios de fondos»" in why for why in said["without_price"])


async def test_a_catalogue_fund_given_by_its_isin_keeps_its_symbol_whatever_its_name(
    api, kernel, schema, monkeypatch
) -> None:
    found = markets()
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(found))
    shot = {
        **SHOT,
        "funds": [
            {"name": "VANGUARD US 500 STK IDX INS PL", "isin": "IE00BFPM9V94", "value": "990"},
            {"name": "Liquidez", "value": "10"},
        ],
    }

    recorded = await api.post(
        "/tools/record_portfolio", json=shot, headers={"x-arga-scopes": "hub:write"}
    )

    said = recorded.json()["content"]
    assert said["recorded"] and said["without_price"] == [] and said["priced_by_isin"] == []
    held = {h["symbol"] for h in await events_of(schema, "finance.holding")}
    assert held == {"0P00011HBK.F", "EUR"}
    assert found.asked == []
