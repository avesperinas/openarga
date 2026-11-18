from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from money_people import OTHER
from test_money_api import (
    book,  # noqa: F401 -- the fixture with the log and the configuration
    event,
)
from test_money_products import READ, WRITE, publish

from arga_tenancy import current_user
from money import book as books
from money.texts import today

ISIN = "IE000W8WMSL2"
LINE = f"{ISIN}:XETR:EUR"
TODAY = today()


@pytest.fixture(autouse=True)
def fresh_cache():
    books._CACHE.clear()
    yield
    books._CACHE.clear()


async def brokerage(api) -> str:
    made = await api.post(
        "/accounts", json={"name": "Brokerage", "type": "etf", "institution": "Test Broker"}
    )
    assert made.status_code == 201, made.text
    return made.json()["key"]


def price(day: date, amount: str) -> dict:
    return {
        **event(
            "finance.price",
            {"symbol": LINE, "on": day.isoformat(), "price": amount, "isin": ISIN},
            f"price:{day}",
        ),
        "ts": datetime.combine(day, datetime.min.time(), tzinfo=UTC),
    }


async def test_a_position_without_a_price_is_worth_what_it_cost(book) -> None:  # noqa: F811
    key = await brokerage(book)
    put = await book.put(
        f"/accounts/{key}/positions",
        json={"symbol": ISIN, "name": "World ETF", "units": "10", "cost": "800"},
    )
    assert put.status_code == 200, put.text
    card = put.json()
    [one] = card["positions"]
    assert (one["price_source"], one["value"], one["gain"]) == ("cost", 800.0, 0.0)
    assert card["cost"] == card["value"] == 800.0 and card["currency"] == "EUR"


async def test_a_price_written_by_hand_values_it_and_one_from_the_hub_replaces_it(
    book,  # noqa: F811
    schema,
) -> None:
    key = await brokerage(book)
    written = (TODAY - timedelta(days=5)).isoformat()
    put = await book.put(
        f"/accounts/{key}/positions",
        json={
            "symbol": ISIN,
            "units": "10",
            "cost": "800",
            "price": "90",
            "price_on": written,
        },
    )
    [one] = put.json()["positions"]
    assert (one["price_source"], one["value"], one["gain"]) == ("manual", 900.0, 100.0)
    assert one["gain_pct"] == 12.5

    await publish(schema, [price(TODAY - timedelta(days=1), "95")])
    books._CACHE.clear()
    [hub] = (await book.get(f"/accounts/{key}/positions")).json()["positions"]
    assert (hub["price_source"], hub["price"], hub["value"]) == ("hub", 95.0, 950.0)

    product = (await book.get(f"/products/{key}")).json()
    assert product["value"] == 950.0


async def test_only_an_investment_product_holds_positions(book) -> None:  # noqa: F811
    refused = await book.put(
        "/accounts/main/positions", json={"symbol": ISIN, "units": "1", "cost": "10"}
    )
    assert refused.status_code == 422
    assert (await book.get("/accounts/main/positions")).status_code == 404
    bad = await book.put(
        "/accounts/main/positions", json={"symbol": ISIN, "units": "0", "cost": "1"}
    )
    assert bad.status_code == 422


async def test_a_position_is_replaced_and_deleted(book) -> None:  # noqa: F811
    key = await brokerage(book)
    path = f"/accounts/{key}/positions"
    await book.put(path, json={"symbol": ISIN, "units": "10", "cost": "800"})
    again = await book.put(path, json={"symbol": ISIN, "units": "12", "cost": "960"})
    assert [p["units"] for p in again.json()["positions"]] == [12.0]
    gone = await book.delete(f"{path}/{ISIN}")
    assert gone.json()["positions"] == []
    assert (await book.delete(f"{path}/{ISIN}")).status_code == 404


async def test_fractional_units_and_prices_are_not_rounded_to_cents(book) -> None:  # noqa: F811
    key = await brokerage(book)
    put = await book.put(
        f"/accounts/{key}/positions",
        json={
            "symbol": ISIN,
            "units": "10.1234",
            "cost": "800",
            "price": "90.1234",
            "price_on": (TODAY - timedelta(days=1)).isoformat(),
        },
    )
    [one] = put.json()["positions"]
    assert (one["units"], one["price"]) == (10.1234, 90.1234)


async def test_what_is_held_is_only_the_persons(book) -> None:  # noqa: F811
    key = await brokerage(book)
    await book.put(f"/accounts/{key}/positions", json={"symbol": ISIN, "units": "1", "cost": "10"})
    token = current_user.set(OTHER)
    try:
        assert (await book.get(f"/accounts/{key}/positions")).status_code == 404
    finally:
        current_user.reset(token)


async def test_the_tools_record_and_read_positions(book) -> None:  # noqa: F811
    await brokerage(book)
    wrote = await book.post(
        "/tools/record_position",
        json={"product": "Brokerage", "symbol": ISIN, "units": "4", "cost": "400", "price": "110"},
        headers=WRITE,
    )
    assert wrote.json()["content"] == {"product": "brokerage", "symbol": ISIN}
    refused = await book.post(
        "/tools/record_position",
        json={"product": "Brokerage", "symbol": ISIN, "units": "4", "cost": "400"},
        headers=READ,
    )
    assert refused.status_code == 403
    read = await book.post("/tools/get_positions", json={"product": "Brokerage"}, headers=READ)
    content = read.json()["content"]
    assert (content["value"], content["gain"]) == (440.0, 40.0)
