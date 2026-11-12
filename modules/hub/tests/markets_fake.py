from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import httpx

Points = list[tuple[date, float | None]]


@dataclass
class Venue:
    code: str
    currency: str
    notation: int
    money: float = 0.0


@dataclass
class Instrument:
    isin: str
    name: str
    entity: str
    subtype: str
    venues: list[Venue]


@dataclass
class Markets:
    instruments: dict[str, Instrument] = field(default_factory=dict)
    names: dict[str, list[str]] = field(default_factory=dict)
    eod: dict[int, tuple[str, Points]] = field(default_factory=dict)
    figi: dict[tuple[str, str], str] = field(default_factory=dict)
    figi_type: dict[str, str] = field(default_factory=dict)
    yahoo: dict[str, tuple[str, Points]] = field(default_factory=dict)
    yahoo_search: dict[str, list[str]] = field(default_factory=dict)
    fx: dict[str, Points] = field(default_factory=dict)
    down: set[str] = field(default_factory=set)
    asked: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        host = request.url.host
        if host in self.down:
            return httpx.Response(503)
        if host == "api.onvista.de":
            return self.onvista(request)
        if host == "api.openfigi.com":
            return self.openfigi(request)
        if host == "query1.finance.yahoo.com":
            return self.yahoo_answer(request)
        if host == "api.frankfurter.dev":
            return self.frankfurter(request)
        return httpx.Response(404)

    def onvista(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1/instruments/")
        if path == "search/facet":
            value = request.url.params["searchValue"]
            isins = [value] if value in self.instruments else self.names.get(value, [])
            results = [
                {
                    "entityType": self.instruments[isin].entity.split("/")[0],
                    "entitySubType": self.instruments[isin].subtype,
                    "entityValue": self.instruments[isin].entity.split("/")[1],
                    "name": self.instruments[isin].name,
                    "isin": isin,
                }
                for isin in isins
                if isin in self.instruments
            ]
            return httpx.Response(
                200, json={"facets": [{"type": "ETF", "results": results}, {"results": None}]}
            )
        entity, _, tail = path.rpartition("/")
        found = next((i for i in self.instruments.values() if i.entity == entity), None)
        if found is None:
            return httpx.Response(404)
        if tail == "snapshot":
            return httpx.Response(
                200,
                json={
                    "instrument": {"entitySubType": found.subtype, "name": found.name},
                    "quoteList": {
                        "list": [
                            {
                                "market": {"codeMarket": v.code, "idNotation": v.notation},
                                "isoCurrency": v.currency,
                                "money": v.money,
                            }
                            for v in found.venues
                        ]
                    },
                },
            )
        notation = int(request.url.params["idNotation"])
        if notation not in self.eod:
            return httpx.Response(404)
        currency, points = self.eod[notation]
        start = date.fromisoformat(request.url.params["startDate"])
        kept = [(d, v) for d, v in points if d >= start and v is not None]
        return httpx.Response(
            200,
            json={
                "isoCurrency": currency,
                "datetimeLast": [
                    int(datetime(d.year, d.month, d.day, 12, tzinfo=UTC).timestamp())
                    for d, _ in kept
                ],
                "last": [v for _, v in kept],
            },
        )

    def openfigi(self, request: httpx.Request) -> httpx.Response:
        answers = []
        for job in json.loads(request.content):
            isin, code = job["idValue"], job.get("exchCode")
            data = [
                {
                    "ticker": ticker,
                    "exchCode": exch,
                    "securityType": self.figi_type.get(isin, "ETP"),
                    "name": isin,
                }
                for (known, exch), ticker in self.figi.items()
                if known == isin and (code is None or exch == code)
            ]
            answers.append({"data": data} if data else {"warning": "No identifier found."})
        return httpx.Response(200, json=answers)

    def yahoo_answer(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/finance/search":
            symbols = self.yahoo_search.get(request.url.params["q"], [])
            return httpx.Response(200, json={"quotes": [{"symbol": s} for s in symbols]})
        symbol = request.url.path.rsplit("/", 1)[-1]
        if symbol not in self.yahoo:
            return httpx.Response(404)
        currency, points = self.yahoo[symbol]
        if "period1" in request.url.params:
            start = datetime.fromtimestamp(int(request.url.params["period1"]), UTC).date()
            points = [(d, v) for d, v in points if d >= start]
        return httpx.Response(200, json=chart(points, currency))

    def frankfurter(self, request: httpx.Request) -> httpx.Response:
        wanted = request.url.params["symbols"]
        if wanted not in self.fx:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "base": "EUR",
                "rates": {d.isoformat(): {wanted: v} for d, v in self.fx[wanted] if v},
            },
        )


def chart(points: Points, currency: str) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {"gmtoffset": 3600, "currency": currency},
                    "timestamp": [
                        int(datetime(d.year, d.month, d.day, 8, tzinfo=UTC).timestamp())
                        for d, _ in points
                    ],
                    "indicators": {"quote": [{"close": [v for _, v in points]}]},
                }
            ],
            "error": None,
        }
    }


QUANTUM = "IE000W8WMSL2"
SP500 = "IE00B5BMR087"


def markets() -> Markets:
    found = Markets()
    found.instruments[QUANTUM] = Instrument(
        QUANTUM,
        "WisdomTree Quantum Computing UCITS ETF - USD ACC",
        "FUND/298266867",
        "ETF",
        [
            Venue("_GAT", "EUR", 5, 600.0),
            Venue("_MIL", "EUR", 2, 400.0),
            Venue("_GER", "EUR", 1, 3500.0),
            Venue("_LSE", "USD", 3, 100.0),
            Venue("_LSE", "GBp", 4, 300000.0),
            Venue("@_WM", "EUR", 6),
        ],
    )
    found.names["WISDOMTREE QUANTUM COMP ETF"] = [QUANTUM]
    found.figi.update(
        {
            (QUANTUM, "GR"): "WQTM",
            (QUANTUM, "IM"): "WQTM",
            (QUANTUM, "LN"): "WQTM",
        }
    )
    found.instruments[SP500] = Instrument(
        SP500,
        "iShares Core S&P 500 UCITS ETF USD Acc.",
        "FUND/26625454",
        "ETF",
        [Venue("_LSE", "USD", 11, 2500.0), Venue("_GER", "EUR", 12, 19000.0)],
    )
    found.figi.update({(SP500, "LN"): "CSPX", (SP500, "GR"): "SXR8"})
    return found
