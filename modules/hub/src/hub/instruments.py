from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Any, Literal

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hub.funds import Fund, catalogue

Kind = Literal["fund", "listed"]

ONVISTA = "https://api.onvista.de/api/v1"
OPENFIGI = "https://api.openfigi.com/v3/mapping"
YAHOO_SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
HEADERS = {"user-agent": "Mozilla/5.0 (arga)"}
TIMEOUT = 20.0
NAV = "@_WM"


@dataclass(frozen=True)
class Venue:
    mic: str
    name: str
    onvista: str
    figi: tuple[str, ...]
    yahoo: str
    currency: str


VENUES = (
    Venue("XETR", "Xetra", "_GER", ("GY", "GR"), ".DE", "EUR"),
    Venue("XMIL", "Borsa Italiana", "_MIL", ("IM",), ".MI", "EUR"),
    Venue("XPAR", "Euronext París", "_PAR", ("FP",), ".PA", "EUR"),
    Venue("XAMS", "Euronext Ámsterdam", "_AMS", ("NA",), ".AS", "EUR"),
    Venue("XLON", "Bolsa de Londres", "_LSE", ("LN",), ".L", "USD"),
    Venue("XSWX", "SIX Swiss Exchange", "_SWX", ("SW", "SE"), ".SW", "CHF"),
    Venue("XNAS", "Nasdaq", "_NMS", ("UW", "US"), "", "USD"),
    Venue("XNYS", "NYSE", "_NYS", ("UN", "US"), "", "USD"),
    Venue("ARCX", "NYSE Arca", "_NAL", ("UP", "US"), "", "USD"),
)
BY_MIC = {venue.mic: venue for venue in VENUES}
BY_ONVISTA = {venue.onvista: venue for venue in VENUES}
EUR_ORDER = ("XETR", "XMIL", "XPAR", "XAMS")
ORDER = {"EUR": EUR_ORDER, "USD": ("ARCX", "XNYS", "XNAS")}
PENCE = {"GBp": "GBP", "GBX": "GBP"}
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class Unresolved(Exception):
    pass


@dataclass(frozen=True)
class Line:
    isin: str
    kind: Kind
    name: str
    currency: str
    since: date
    mic: str | None = None
    yahoo: str | None = None
    onvista_entity: str | None = None
    onvista_notation: int | None = None

    @property
    def symbol(self) -> str:
        if not self.mic:
            return self.isin
        return f"{self.isin}:{self.mic}:{PENCE.get(self.currency, self.currency)}"

    @property
    def where(self) -> str:
        venue = BY_MIC.get(self.mic or "")
        return f"{venue.name}, {self.currency}" if venue else f"valor liquidativo, {self.currency}"

    def stored(self) -> dict[str, Any]:
        found = asdict(self)
        found["since"] = self.since.isoformat()
        return {key: value for key, value in found.items() if value is not None}

    @classmethod
    def from_stored(cls, raw: dict[str, Any]) -> Line | None:
        try:
            return cls(**{**raw, "since": date.fromisoformat(raw["since"])})
        except (KeyError, TypeError, ValueError):
            return None


def valid_isin(isin: str) -> bool:
    if not ISIN.match(isin):
        return False
    digits = "".join(str(int(char, 36)) for char in isin[:-1])
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char) * (2 if index % 2 == 0 else 1)
        total += number // 10 + number % 10
    return (10 - total % 10) % 10 == int(isin[-1])


def in_catalogue(isin: str) -> Fund | None:
    return next((fund for fund in catalogue() if fund.isin == isin), None)


async def get(client: httpx.AsyncClient, url: str, **params: Any) -> Any | None:
    try:
        response = await client.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


async def onvista_search(client: httpx.AsyncClient, value: str) -> list[dict[str, Any]]:
    body = await get(client, f"{ONVISTA}/instruments/search/facet", searchValue=value)
    if not isinstance(body, dict):
        return []
    return [
        found
        for facet in body.get("facets") or []
        for found in facet.get("results") or []
        if found.get("isin")
    ]


async def isin_of(client: httpx.AsyncClient, name: str) -> str:
    found = {hit["isin"] for hit in await onvista_search(client, name)}
    if len(found) == 1:
        return found.pop()
    raise Unresolved(
        f"no sé qué valor es «{name}»"
        + (f" (puede ser {len(found)})" if found else "")
        + ": dime su ISIN"
    )


@dataclass(frozen=True)
class Quote:
    venue: Venue | None
    currency: str
    notation: int
    traded: float


async def onvista_quotes(
    client: httpx.AsyncClient, isin: str
) -> tuple[str, str, str, list[Quote]] | None:
    hits = [hit for hit in await onvista_search(client, isin) if hit["isin"] == isin]
    if not hits:
        return None
    hit = hits[0]
    entity = f"{hit['entityType']}/{hit['entityValue']}"
    body = await get(client, f"{ONVISTA}/instruments/{entity}/snapshot")
    if not isinstance(body, dict):
        return None
    instrument = body.get("instrument") or {}
    subtype = instrument.get("entitySubType") or hit.get("entitySubType")
    kind: Kind = "fund" if subtype == "FUND" else "listed"
    quotes = []
    for quote in (body.get("quoteList") or {}).get("list") or []:
        market = quote.get("market") or {}
        code, notation = market.get("codeMarket"), market.get("idNotation")
        if not notation or not quote.get("isoCurrency"):
            continue
        venue = BY_ONVISTA.get(code)
        if venue is None and code != NAV:
            continue
        quotes.append(
            Quote(venue, quote["isoCurrency"], int(notation), float(quote.get("money") or 0))
        )
    return entity, kind, instrument.get("name") or hit.get("name") or isin, quotes


async def figi(
    client: httpx.AsyncClient, isin: str, venue: Venue | None = None, currency: str | None = None
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for code in venue.figi if venue else (None,):
        job: dict[str, Any] = {"idType": "ID_ISIN", "idValue": isin}
        if code:
            job["exchCode"] = code
        if currency:
            job["currency"] = currency
        jobs.append(job)
    try:
        response = await client.post(OPENFIGI, json=jobs, headers=HEADERS, timeout=TIMEOUT)
        body = response.json() if response.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return []
    found = [one for answer in body if isinstance(answer, dict) for one in answer.get("data") or []]
    if not found and currency:
        return await figi(client, isin, venue)
    return found


async def yahoo_symbol(
    client: httpx.AsyncClient, isin: str, venue: Venue | None, currency: str
) -> str | None:
    if venue is not None:
        tickers = [found["ticker"] for found in await figi(client, isin, venue, currency)]
        if tickers:
            return f"{tickers[0]}{venue.yahoo}"
    body = await get(client, YAHOO_SEARCH, q=isin, quotesCount=10, newsCount=0)
    quotes = body.get("quotes") or [] if isinstance(body, dict) else []
    for quote in quotes:
        symbol = quote.get("symbol") or ""
        if venue is None and symbol.startswith("0P"):
            return symbol
        if venue is not None and venue.yahoo and symbol.endswith(venue.yahoo):
            return symbol
        if venue is not None and not venue.yahoo and "." not in symbol:
            return symbol
    return None


def pick(quotes: list[Quote], mic: str | None, currency: str | None, account: str) -> Quote | None:
    listed = [quote for quote in quotes if quote.venue is not None]
    if mic:
        return next(
            (
                quote
                for quote in listed
                if quote.venue.mic == mic and (currency is None or quote.currency == currency)
            ),
            None,
        )
    wanted = currency or account
    same = [quote for quote in listed if quote.currency == wanted]
    for preferred in ORDER.get(wanted, ()):
        hit = next((quote for quote in same if quote.venue.mic == preferred), None)
        if hit:
            return hit
    if same:
        return max(same, key=lambda quote: quote.traded)
    return max(listed, key=lambda quote: quote.traded) if listed and not currency else None


async def resolve(
    client: httpx.AsyncClient,
    *,
    name: str,
    since: date,
    isin: str | None = None,
    mic: str | None = None,
    currency: str | None = None,
    account: str = "EUR",
) -> Line:
    if mic is not None and mic not in BY_MIC:
        raise Unresolved(f"no conozco la bolsa {mic}: {', '.join(BY_MIC)}")
    isin = (isin or await isin_of(client, name)).strip().upper()
    if not valid_isin(isin):
        raise Unresolved(f"«{isin}» no es un ISIN")
    found = await onvista_quotes(client, isin)
    if found is not None:
        entity, kind, label, quotes = found
        if kind == "fund":
            return await fund_line(client, isin, label, since, account, entity, quotes)
        quote = pick(quotes, mic, currency, account)
        if quote is None:
            where = ", ".join(
                sorted({f"{q.venue.mic} {q.currency}" for q in quotes if q.venue is not None})
            )
            raise Unresolved(
                f"{isin} no cotiza en {mic or ''} {currency or account}".replace("  ", " ")
                + (f"; cotiza en {where}" if where else "")
            )
        line = Line(
            isin,
            "listed",
            label,
            quote.currency,
            since,
            quote.venue.mic,
            None,
            entity,
            quote.notation,
        )
        return replace(line, yahoo=await yahoo_symbol(client, isin, quote.venue, quote.currency))
    return await figi_line(client, isin, name, since, mic, currency, account)


async def fund_line(
    client: httpx.AsyncClient,
    isin: str,
    label: str,
    since: date,
    account: str,
    entity: str,
    quotes: list[Quote],
) -> Line:
    navs = [quote for quote in quotes if quote.venue is None]
    nav = next((quote for quote in navs if quote.currency == account), navs[0] if navs else None)
    yahoo = await yahoo_symbol(client, isin, None, account)
    if nav is None and yahoo is None:
        raise Unresolved(f"no encuentro el valor liquidativo de {isin}")
    return Line(
        isin,
        "fund",
        label,
        nav.currency if nav else account,
        since,
        None,
        yahoo,
        entity if nav else None,
        nav.notation if nav else None,
    )


async def figi_line(
    client: httpx.AsyncClient,
    isin: str,
    name: str,
    since: date,
    mic: str | None,
    currency: str | None,
    account: str,
) -> Line:
    known = await figi(client, isin)
    if not known:
        raise Unresolved(f"no encuentro {isin} en onvista ni en OpenFIGI")
    if all(found.get("securityType") == "Open-End Fund" for found in known):
        yahoo = await yahoo_symbol(client, isin, None, account)
        if yahoo is None:
            raise Unresolved(f"no encuentro el valor liquidativo de {isin}")
        return Line(isin, "fund", known[0].get("name") or name, account, since, None, yahoo)
    codes = {found.get("exchCode"): found.get("ticker") for found in known}
    first = ORDER.get(currency or account, ())
    order = [mic] if mic else [*first, *(m for m in BY_MIC if m not in first)]
    for candidate in order:
        venue = BY_MIC[candidate]
        ticker = next((codes[code] for code in venue.figi if codes.get(code)), None)
        if ticker is None:
            continue
        return Line(
            isin,
            "listed",
            known[0].get("name") or name,
            currency or venue.currency,
            since,
            venue.mic,
            f"{ticker}{venue.yahoo}",
        )
    raise Unresolved(f"{isin} no cotiza en {mic or 'ninguna bolsa que conozca'}")


PRICES = "prices"
FIND = text("""
    select id, config from hub.hub_connection
    where provider = :provider order by created_at limit 1
""")
STORE = text("""
    update hub.hub_connection
    set config = config || jsonb_build_object('instruments', cast(:instruments as jsonb))
    where id = :id
""")


def stored(config: dict[str, Any] | None) -> list[Line]:
    raw = (config or {}).get("instruments") or []
    return [line for one in raw if isinstance(one, dict) and (line := Line.from_stored(one))]


async def remember(connection: AsyncConnection, lines: list[Line]) -> bool:
    row = (await connection.execute(FIND, {"provider": PRICES})).first()
    if row is None:
        return False
    known = {line.symbol: line for line in stored(row.config)}
    for line in lines:
        before = known.get(line.symbol)
        known[line.symbol] = replace(line, since=min(line.since, before.since)) if before else line
    await connection.execute(
        STORE,
        {
            "id": row.id,
            "instruments": json.dumps([line.stored() for line in known.values()]),
        },
    )
    return True
