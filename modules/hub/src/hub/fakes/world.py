from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

Answer = Callable[[httpx.Request], httpx.Response]


def today() -> date:
    return datetime.now(UTC).date()


def stamp(day: date, hour: int = 18) -> str:
    return f"{day.isoformat()}T{hour:02d}:00Z"


def holidays(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/AvailableCountries"):
        return httpx.Response(200, json=[{"countryCode": "ES", "name": "Spain"}])
    year = int(request.url.path.rstrip("/").split("/")[-2])
    found = [
        ("01-01", "New Year's Day", True, None),
        ("05-01", "Labour Day", True, None),
        ("07-07", "Regional Day", False, ["ES-NC"]),
        ("12-25", "Christmas Day", True, None),
    ]
    return httpx.Response(
        200,
        json=[
            {
                "date": f"{year}-{day}",
                "localName": name,
                "name": name,
                "global": everywhere,
                "counties": counties,
                "types": ["Public"],
            }
            for day, name, everywhere, counties in found
        ],
    )


def formula1(request: httpx.Request) -> httpx.Response:
    year = int(request.url.path.split("/")[3])
    first = max(date(year, 3, 1), today() - timedelta(days=30))
    races = []
    for number in range(4):
        sunday = first + timedelta(days=(6 - first.weekday()) % 7 + 14 * number)
        if sunday.year != year:
            break
        races.append(
            {
                "season": str(year),
                "round": str(number + 1),
                "raceName": f"Example Grand Prix {number + 1}",
                "Circuit": {
                    "circuitName": "Example Circuit",
                    "Location": {"locality": "Example Town", "country": "Nowhere"},
                },
                "date": sunday.isoformat(),
                "time": "13:00:00Z",
                "Qualifying": {
                    "date": (sunday - timedelta(days=1)).isoformat(),
                    "time": "14:00:00Z",
                },
            }
        )
    return httpx.Response(200, json={"MRData": {"RaceTable": {"Races": races}}})


def game(number: int, day: date, home: str, away: str, played: bool) -> dict[str, Any]:
    side = lambda where, team, score: {  # noqa: E731
        "homeAway": where,
        "team": {"displayName": team},
        "score": {"displayValue": score} if played else None,
    }
    return {
        "id": f"fake-{number}",
        "date": stamp(day),
        "timeValid": True,
        "competitions": [
            {
                "status": {"type": {"name": "STATUS_FULL_TIME" if played else "STATUS_SCHEDULED"}},
                "venue": {"fullName": "Example Stadium", "address": {"city": "Example Town"}},
                "competitors": [side("home", home, "2"), side("away", away, "1")],
            }
        ],
    }


def espn(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/teams"):
        teams = [
            {"team": {"id": "11", "displayName": "Example FC"}},
            {"team": {"id": "12", "displayName": "Sample United"}},
        ]
        return httpx.Response(200, json={"sports": [{"leagues": [{"teams": teams}]}]})
    if "/teams/" not in path or "/soccer/uefa" in path:
        return httpx.Response(404)
    start = today() - timedelta(days=14)
    games = [
        game(
            n, start + timedelta(days=7 * n), *pair, played=start + timedelta(days=7 * n) < today()
        )
        for n, pair in enumerate(
            [("Example FC", "Sample United"), ("Sample City", "Example FC")] * 3
        )
    ]
    upcoming = "fixture=true" in str(request.url)
    chosen = [g for g in games if (g["date"] >= stamp(today(), 0)) == upcoming]
    return httpx.Response(200, json={"events": chosen})


def ical(request: httpx.Request) -> httpx.Response:
    start = today()
    events = "".join(
        "BEGIN:VEVENT\r\n"
        f"UID:fake-{number}@example.org\r\n"
        f"DTSTAMP:{start.strftime('%Y%m%d')}T000000Z\r\n"
        f"DTSTART:{(start + timedelta(days=number * 3)).strftime('%Y%m%d')}T170000Z\r\n"
        f"DTEND:{(start + timedelta(days=number * 3)).strftime('%Y%m%d')}T180000Z\r\n"
        f"SUMMARY:Example event {number + 1}\r\n"
        "END:VEVENT\r\n"
        for number in range(5)
    )
    body = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//fake//EN\r\n{events}END:VCALENDAR\r\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/calendar"})


RATES = {"USD": 1.08, "GBP": 0.85, "CHF": 0.94, "JPY": 162.0, "EUR": 1.0}


def seed(text: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(text))


def weekdays(first: date, last: date) -> list[date]:
    return [
        first + timedelta(days=n)
        for n in range((last - first).days + 1)
        if (first + timedelta(days=n)).weekday() < 5
    ]


def close(symbol: str, day: date) -> float:
    base = 20 + seed(symbol) % 480
    wave = ((day.toordinal() * 7 + seed(symbol)) % 21 - 10) / 400
    return round(base * (1 + wave + (day.toordinal() % 365) / 3650), 4)


def yahoo(request: httpx.Request) -> httpx.Response:
    if "/finance/search" in request.url.path:
        return httpx.Response(200, json={"quotes": []})
    symbol = request.url.path.rsplit("/", 1)[-1]
    days = weekdays(today() - timedelta(days=92), today() - timedelta(days=1))
    currency = "USD" if "." not in symbol and "=" not in symbol else "EUR"
    if symbol.endswith("=X"):
        currency = symbol[3:6]
    return httpx.Response(
        200,
        json={
            "chart": {
                "result": [
                    {
                        "meta": {"gmtoffset": 3600, "currency": currency},
                        "timestamp": [
                            int(datetime(d.year, d.month, d.day, 16, tzinfo=UTC).timestamp())
                            for d in days
                        ],
                        "indicators": {"quote": [{"close": [close(symbol, d) for d in days]}]},
                    }
                ],
                "error": None,
            }
        },
    )


def frankfurter(request: httpx.Request) -> httpx.Response:
    span = request.url.path.removeprefix("/v1/")
    base = request.url.params.get("base", "EUR")
    wanted = request.url.params.get("symbols", "USD").split(",")

    def rate(currency: str) -> float:
        return round(RATES.get(currency, 1.0) / RATES.get(base, 1.0), 5)

    if ".." in span:
        first, _, last = span.partition("..")
        days = weekdays(date.fromisoformat(first), date.fromisoformat(last or today().isoformat()))
        rates = {d.isoformat(): {c: rate(c) for c in wanted} for d in days}
        return httpx.Response(200, json={"base": base, "rates": rates})
    day = today().isoformat() if span in ("latest", "") else span
    return httpx.Response(
        200, json={"base": base, "date": day, "rates": {c: rate(c) for c in wanted}}
    )


ROUTES: list[tuple[str, str, Answer]] = [
    ("query1.finance.yahoo.com", "", yahoo),
    ("api.frankfurter.dev", "", frankfurter),
    ("date.nager.at", "", holidays),
    ("api.jolpi.ca", "", formula1),
    ("site.api.espn.com", "", espn),
]
ICAL = re.compile(r"\.ics$|ical|calendar", re.IGNORECASE)
