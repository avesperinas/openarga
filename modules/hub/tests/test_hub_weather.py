from __future__ import annotations

import secrets
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import text

from hub import capabilities
from hub.providers import weather

TOKEN = secrets.token_hex(16)
KYOTO = {"lat": 35.01, "lon": 135.77}


def archive() -> dict:
    days, highs, lows, rain = [], [], [], []
    last = date.today().year - 1
    day = date(last - 9, 1, 1)
    while day <= date(last, 12, 31):
        days.append(day.isoformat())
        highs.append(8.0 if day.month == 1 else 32.0 if day.month == 8 else 20.0)
        lows.append(1.0 if day.month == 1 else 24.0 if day.month == 8 else 12.0)
        rain.append(4.0 if day.month == 1 and day.day % 4 == 0 else 0.0)
        day += timedelta(days=1)
    return {
        "timezone": "Asia/Tokyo",
        "daily": {
            "time": days,
            "temperature_2m_max": highs,
            "temperature_2m_min": lows,
            "precipitation_sum": rain,
        },
    }


class OpenMeteo:
    def __init__(self) -> None:
        self.down = False
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if self.down:
            raise httpx.ConnectError("sin red", request=request)
        if request.url.host == "archive-api.open-meteo.com":
            return httpx.Response(200, json=archive())
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Tokyo",
                "daily": {
                    "time": ["2027-11-01", "2027-11-02"],
                    "weather_code": [0, 63],
                    "temperature_2m_max": [17.24, 15.0],
                    "temperature_2m_min": [8.0, 9.31],
                    "precipitation_probability_max": [5, 80],
                },
            },
        )


@pytest.fixture
def open_meteo(monkeypatch) -> OpenMeteo:
    fake = OpenMeteo()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(weather, "CACHE", {})
    return fake


def ask(api, capability: str, body: dict):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "travel"},
    )


async def runs(api) -> list[str]:
    listed = (await api.get("/connections")).json()
    [connection] = [c for c in listed if c["provider"] == "open_meteo"]
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    return [run["outcome"] for run in ficha["runs"]]


async def test_the_forecast_says_each_day_in_words_and_asks_once(api, schema, open_meteo) -> None:
    async with schema.connect() as connection:
        before = await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )

    first = (await ask(api, "weather.forecast", KYOTO)).json()
    again = (await ask(api, "weather.forecast", KYOTO)).json()

    days = first["weather"]["days"]
    assert first["failed"] is None and first["weather"]["timezone"] == "Asia/Tokyo"
    assert [(d["day"], d["sky"], d["max_c"], d["rain_chance"]) for d in days] == [
        ("2027-11-01", "despejado", 17.2, 5),
        ("2027-11-02", "lluvia", 15.0, 80),
    ]
    assert again == first and len(open_meteo.asked) == 1
    assert await runs(api) == ["ok", "ok"]
    async with schema.connect() as connection:
        assert before == await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )


async def test_the_climate_is_the_average_of_ten_years(api, open_meteo) -> None:
    answer = (await ask(api, "weather.climate", KYOTO)).json()

    months = {m["month"]: m for m in answer["weather"]["months"]}
    assert len(months) == 12
    assert (months[1]["max_c"], months[1]["min_c"]) == (8.0, 1.0)
    assert months[1]["rain_days"] == 7.0 and months[1]["rain_mm"] == 28
    assert (months[8]["max_c"], months[8]["rain_days"]) == (32.0, 0.0)
    sent = open_meteo.asked[0].url.params
    assert (
        sent["start_date"].endswith("-01-01") and int(sent["end_date"][:4]) == date.today().year - 1
    )


async def test_open_meteo_down_is_said_and_seen(api, open_meteo) -> None:
    open_meteo.down = True

    answer = (await ask(api, "weather.forecast", KYOTO)).json()

    assert answer["weather"] is None and "no contestó" in answer["failed"]
    assert await runs(api) == ["error"]
