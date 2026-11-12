from __future__ import annotations

import secrets

import httpx
import pytest
from sqlalchemy import text

from hub import capabilities
from hub.providers import fx

TOKEN = secrets.token_hex(16)


class Frankfurter:
    def __init__(self) -> None:
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if request.url.params["base"] == "VND":
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(
            200,
            json={"amount": 1.0, "base": "JPY", "date": "2026-10-02", "rates": {"EUR": 0.00565}},
        )


@pytest.fixture
def frankfurter(monkeypatch) -> Frankfurter:
    fake = Frankfurter()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(fx, "CACHE", {})
    return fake


def ask(api, body: dict):
    return api.post(
        "/capabilities/fx.rate",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "travel"},
    )


async def test_the_rate_of_a_day_says_which_working_day_it_is(api, schema, frankfurter) -> None:
    async with schema.connect() as connection:
        before = await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )

    first = (await ask(api, {"currency": "jpy", "day": "2026-10-04"})).json()
    again = (await ask(api, {"currency": "JPY", "day": "2026-10-04"})).json()

    assert first == {"rate": 0.00565, "date": "2026-10-02", "failed": None}
    assert again == first and len(frankfurter.asked) == 1
    [request] = frankfurter.asked
    assert request.url.path == "/v1/2026-10-04" and request.url.params["symbols"] == "EUR"
    async with schema.connect() as connection:
        assert before == await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )


async def test_euros_are_one_and_an_unpublished_currency_is_said(api, frankfurter) -> None:
    euros = (await ask(api, {"currency": "EUR", "day": "2026-10-04"})).json()
    dong = (await ask(api, {"currency": "VND", "day": "2026-10-04"})).json()

    assert (euros["rate"], euros["failed"]) == (1.0, None)
    assert dong["rate"] is None and "VND" in dong["failed"]
    assert len(frankfurter.asked) == 1
