from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from hub.declare import Provider, Sync
from hub.instruments import ONVISTA, PENCE, Line, stored
from hub.providers import Fetched, SourceError

PROVIDER = "prices"
PRICE = "finance.price"
EURUSD = "EURUSD=X"
RANGE = "3mo"
RECENT = timedelta(days=92)
BEFORE = timedelta(days=10)
YEAR = timedelta(days=365)
PLACES = Decimal("0.000001")
RATES = "https://api.frankfurter.dev/v1/{start}..{end}"
HEADERS = {"user-agent": "Mozilla/5.0 (arga)"}


SOURCES_VARIABLE = "PRICES_SOURCES"
KNOWN_SOURCES = ("yahoo", "onvista")


def sources() -> tuple[str, ...]:
    raw = os.environ.get(SOURCES_VARIABLE, ",".join(KNOWN_SOURCES))
    chosen = tuple(one for one in (part.strip().lower() for part in raw.split(",")) if one)
    unknown = [one for one in chosen if one not in KNOWN_SOURCES]
    if unknown:
        raise SourceError(f"{SOURCES_VARIABLE} names unknown sources: {', '.join(unknown)}")
    return chosen


def base_url() -> str:
    return os.environ.get("PRICES_URL", "https://query1.finance.yahoo.com").rstrip("/")


def closes(body: dict[str, Any]) -> dict[date, Decimal]:
    try:
        result = body["chart"]["result"][0]
        stamps = result.get("timestamp") or []
        values = result["indicators"]["quote"][0].get("close") or []
        offset = int(result.get("meta", {}).get("gmtoffset") or 0)
    except (KeyError, IndexError, TypeError):
        return {}
    found: dict[date, Decimal] = {}
    for stamp, value in zip(stamps, values, strict=False):
        price = positive(value)
        if price is None:
            continue
        day = datetime.fromtimestamp(int(stamp) + offset, UTC).date()
        found[day] = price
    return found


def positive(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        return None
    return price if price > 0 else None


def quoted_in(body: dict[str, Any]) -> str | None:
    try:
        return body["chart"]["result"][0]["meta"].get("currency")
    except (KeyError, IndexError, TypeError):
        return None


def on_or_before(series: dict[date, Decimal], day: date) -> Decimal | None:
    known = [d for d in series if d <= day]
    return series[max(known)] if known else None


def in_euros(
    series: dict[date, Decimal], currency: str, rates: dict[date, Decimal]
) -> dict[date, Decimal]:
    if currency == "EUR":
        return series
    out = {}
    for day, price in series.items():
        rate = on_or_before(rates, day)
        if rate:
            out[day] = price / rate
    return out


def in_units(currency: str, series: dict[date, Decimal]) -> tuple[str, dict[date, Decimal]]:
    if currency in PENCE:
        return PENCE[currency], {day: price / 100 for day, price in series.items()}
    return currency, series


@dataclass
class Priced:
    symbol: str
    name: str
    series: dict[date, Decimal]
    extra: dict[str, str] = field(default_factory=dict)


def events(prices: list[Priced]) -> list[dict[str, Any]]:
    found = []
    for priced in sorted(prices, key=lambda one: one.symbol):
        for day, price in sorted(priced.series.items()):
            value = str(price.quantize(PLACES))
            found.append(
                {
                    "ts": datetime.combine(day, datetime.min.time(), UTC).isoformat(),
                    "type": PRICE,
                    "payload": {
                        "symbol": priced.symbol,
                        "on": day.isoformat(),
                        "price": value,
                        "currency": "EUR",
                        "name": priced.name,
                        **priced.extra,
                    },
                    "dedup_hash": f"{PROVIDER}:{priced.symbol}:{day.isoformat()}:{value}",
                }
            )
    return found


async def chart(
    client: httpx.AsyncClient, symbol: str, since: date | None = None
) -> tuple[str | None, dict[date, Decimal]]:
    params: dict[str, Any] = {"interval": "1d"}
    if since is None:
        params["range"] = RANGE
    else:
        params["period1"] = int(datetime.combine(since, datetime.min.time(), UTC).timestamp())
        params["period2"] = int(datetime.now(UTC).timestamp())
    try:
        response = await client.get(
            f"{base_url()}/v8/finance/chart/{symbol}", params=params, headers=HEADERS, timeout=20.0
        )
    except httpx.HTTPError as error:
        raise SourceError(
            f"Yahoo does not answer ({type(error).__name__})", transient=True
        ) from error
    if response.status_code == 429:
        raise SourceError("Yahoo asks to wait", rate_limited=True)
    if response.status_code >= 500:
        raise SourceError(f"Yahoo falla ({response.status_code})", transient=True)
    if response.status_code >= 400:
        raise SourceError(f"Yahoo does not know {symbol} ({response.status_code})")
    try:
        body = response.json()
    except ValueError as error:
        raise SourceError("Yahoo answers without data") from error
    return quoted_in(body), closes(body)


async def series(client: httpx.AsyncClient, symbol: str) -> dict[date, Decimal]:
    return (await chart(client, symbol))[1]


async def onvista(
    client: httpx.AsyncClient, line: Line, start: date, today: date
) -> tuple[str | None, dict[date, Decimal]]:
    found: dict[date, Decimal] = {}
    currency = None
    since = start
    while since <= today:
        try:
            response = await client.get(
                f"{ONVISTA}/instruments/{line.onvista_entity}/eod_history",
                params={
                    "idNotation": line.onvista_notation,
                    "range": "Y1",
                    "startDate": since.isoformat(),
                },
                headers=HEADERS,
                timeout=20.0,
            )
            body = response.json() if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError) as error:
            raise SourceError(f"onvista does not answer ({type(error).__name__})") from error
        if not isinstance(body, dict):
            raise SourceError(f"onvista gives no closes for {line.isin}")
        currency = body.get("isoCurrency") or currency
        for stamp, value in zip(
            body.get("datetimeLast") or [], body.get("last") or [], strict=False
        ):
            price = positive(value)
            if price is not None:
                found[datetime.fromtimestamp(int(stamp), UTC).date()] = price
        since += YEAR
    return currency, found


async def rates(client: httpx.AsyncClient, currency: str, start: date, today: date) -> dict:
    try:
        response = await client.get(
            RATES.format(start=start.isoformat(), end=today.isoformat()),
            params={"base": "EUR", "symbols": currency},
            headers=HEADERS,
            timeout=20.0,
            follow_redirects=True,
        )
        body = response.json() if response.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        body = {}
    found = {}
    for day, values in (body.get("rates") or {}).items() if isinstance(body, dict) else []:
        rate = positive((values or {}).get(currency))
        if rate is not None:
            found[date.fromisoformat(day)] = rate
    if found:
        return found
    return await series(client, EURUSD if currency == "USD" else f"EUR{currency}=X")


async def line_series(
    client: httpx.AsyncClient, line: Line, start: date, today: date
) -> tuple[str, dict[date, Decimal], list[str]]:
    currency, found, problems = line.currency, {}, []
    chosen = sources()
    if line.yahoo and "yahoo" in chosen:
        try:
            unit, got = await chart(client, line.yahoo, start)
            currency, found = in_units(unit or line.currency, got)
        except SourceError as error:
            if error.rate_limited:
                raise
            problems.append(str(error))
    if line.onvista_entity and line.onvista_notation and "onvista" in chosen:
        try:
            unit, got = await onvista(client, line, start, today)
            unit, got = in_units(unit or line.currency, got)
            if not found:
                currency = unit
            if unit == currency:
                found = {**got, **found}
        except SourceError as error:
            problems.append(str(error))
    return currency, found, problems


async def fetch(
    client: httpx.AsyncClient,
    lines: list[Line] | None = None,
    filled: dict[str, str] | None = None,
    today: date | None = None,
) -> Fetched:
    today = today or datetime.now(UTC).date()
    lines, filled = lines or [], dict(filled or {})
    found: list[Priced] = []
    failed: list[str] = []
    fx: dict[str, dict[date, Decimal]] = {}

    def starts(line: Line) -> date:
        done = filled.get(line.symbol)
        first = line.since - BEFORE
        return (
            first if done is None or done > line.since.isoformat() else max(first, today - RECENT)
        )

    earliest = min([today - RECENT, *(starts(line) for line in lines)])

    async def to_euros(series: dict[date, Decimal], currency: str) -> dict[date, Decimal]:
        if currency == "EUR":
            return series
        if currency not in fx:
            fx[currency] = await rates(client, currency, earliest, today)
        return in_euros(series, currency, fx[currency])

    for line in lines:
        currency, got, problems = await line_series(client, line, starts(line), today)
        try:
            priced = await to_euros(got, currency) if got else {}
        except SourceError as error:
            problems.append(f"no exchange rate for {currency}: {error}")
            priced = {}
        if not priced:
            failed.append(
                f"{line.name} ({line.isin or line.yahoo}, {line.where}): "
                + ("; ".join(problems) or "no closes")
                + "; type its price by hand in Hub"
            )
            continue
        extra = {"kind": line.kind, "quote_currency": currency}
        if line.isin:
            extra["isin"] = line.isin
        if line.mic:
            extra["mic"] = line.mic
        found.append(Priced(line.symbol, line.name, priced, extra))
        filled[line.symbol] = line.since.isoformat()

    if not found and failed:
        raise SourceError(f"gave no price ({'; '.join(failed[:3])}…)")
    return Fetched(
        events(found),
        problem=f"No price for {'; '.join(failed)}" if failed else None,
        state={"filled": filled} if lines else None,
    )


def typed(symbol: str, name: str, on: date, price: Decimal, line: Line | None) -> dict[str, Any]:
    extra = {"kind": line.kind} if line else {}
    if line and line.isin:
        extra["isin"] = line.isin
    if line and line.mic:
        extra["mic"] = line.mic
    return events([Priced(symbol, name, {on: price}, extra)])[0]


async def sync(client: httpx.AsyncClient, _secrets: dict[str, str], connection: Any) -> Fetched:
    config = getattr(connection, "config", None) or {}
    return await fetch(client, stored(config), config.get("filled"))


SOURCES = (
    Provider(
        id="prices",
        name="Prices",
        category="finance",
        description="The daily value of the funds, ETFs, ETCs and shares you hold, by"
        " ISIN or ticker, so Money moves your portfolios between one snapshot and the"
        " next. Public and keyless, from Yahoo Finance and onvista (the instance picks"
        " which with PRICES_SOURCES); fetched once a day. What no source prices can be"
        " typed by hand.",
        capabilities=("sync",),
        emits=("finance.price",),
        available=True,
        single=True,
        schedule="30 6 * * 1-6",
        sync=Sync("prices", sync),
    ),
)
