from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from arga_contracts import sources
from hub.funds import Fund
from hub.providers import SourceError, prices


def stamp(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, 13, 30, tzinfo=UTC).timestamp())


def chart(points: list[tuple[date, float | None]], offset: int = -14400) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {"gmtoffset": offset},
                    "timestamp": [stamp(d) for d, _ in points],
                    "indicators": {"quote": [{"close": [v for _, v in points]}]},
                }
            ],
            "error": None,
        }
    }


D1, D2 = date(2030, 10, 1), date(2030, 10, 2)
FUNDS = (
    Fund("Fondo en euros", "FUND.F", "EUR"),
    Fund("ETF en dólares", "ETF", "USD"),
)


def yahoo(answers: dict[str, httpx.Response]):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host != "query1.finance.yahoo.com":
            return httpx.Response(404)
        symbol = request.url.path.rsplit("/", 1)[-1]
        assert request.url.params["interval"] == "1d"
        return answers.get(symbol, httpx.Response(404))

    return handle


@pytest.fixture(autouse=True)
def few_funds(monkeypatch):
    monkeypatch.setattr(prices, "catalogue", lambda: FUNDS)


async def run(answers: dict[str, httpx.Response]) -> list[dict]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(yahoo(answers))) as client:
        return (await prices.sync(client, {}, None)).events


async def test_each_close_goes_out_in_euros_on_its_market_day() -> None:
    out = await run(
        {
            "FUND.F": httpx.Response(200, json=chart([(D1, 600.0), (D2, None)], offset=7200)),
            "ETF": httpx.Response(200, json=chart([(D1, 110.0), (D2, 121.0)])),
            "EURUSD=X": httpx.Response(200, json=chart([(D1, 1.1), (D2, 1.21)], offset=3600)),
        }
    )

    by = {(e["payload"]["symbol"], e["payload"]["on"]): e["payload"]["price"] for e in out}
    assert by == {
        ("FUND.F", "2030-10-01"): "600.000000",
        ("ETF", "2030-10-01"): "100.000000",
        ("ETF", "2030-10-02"): "100.000000",
    }
    for event in out:
        sources.check(event["type"], event["payload"])
        assert event["payload"]["currency"] == "EUR"
    assert len({e["dedup_hash"] for e in out}) == 3


async def test_a_symbol_that_fails_does_not_stop_the_rest() -> None:
    out = await run(
        {
            "FUND.F": httpx.Response(200, json=chart([(D1, 600.0)])),
            "EURUSD=X": httpx.Response(200, json=chart([(D1, 1.1)])),
        }
    )
    assert {e["payload"]["symbol"] for e in out} == {"FUND.F"}


async def test_when_every_symbol_fails_the_pass_fails() -> None:
    with pytest.raises(SourceError, match="gave no price"):
        await run({"EURUSD=X": httpx.Response(200, json=chart([(D1, 1.1)]))})


async def test_being_asked_to_wait_stops_the_pass() -> None:
    with pytest.raises(SourceError) as raised:
        await run({"EURUSD=X": httpx.Response(429)})
    assert raised.value.rate_limited


def test_a_dollar_price_without_a_rate_yet_is_left_out() -> None:
    priced = prices.in_euros({D1: Decimal(10)}, "USD", {D2: Decimal("1.1")})
    assert priced == {}
