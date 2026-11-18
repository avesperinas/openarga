import secrets
import types
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from hub import capabilities, catalogue, fake
from hub.fakes import bank, doubles, google

TOKEN = secrets.token_hex(16)
CONFIGS = {
    "holidays": {"country": "ES", "region": "ES-NC"},
    "football": {"team": "11", "league": "esp.1", "team_name": "Example FC"},
    "formula1": {"sessions": ["race", "qualifying"]},
    "ical": {"url": "https://calendar.example.org/team.ics"},
    "enable_banking": {
        "bank": bank.BANK,
        "accounts": [
            {
                "uid": "uid-of-this-session",
                "key": bank.ACCOUNT,
                "name": "Payroll account",
                "iban": bank.IBAN,
                "iban_tail": bank.IBAN[-4:],
                "kind": "checking",
            }
        ],
    },
    "prices": {
        "instruments": [
            {
                "isin": "IE00BK5BQT80",
                "kind": "listed",
                "name": "Example world ETF",
                "currency": "EUR",
                "since": "2026-01-02",
                "mic": "XETR",
                "yahoo": "VWCE.DE",
            }
        ]
    },
}
SECRETS = {
    "ical_private": {"url": "https://calendar.example.org/private.ics"},
    "enable_banking": {"app_id": bank.APP_ID, "private_key": bank.PEM},
    "google_health": {
        "client_id": google.CLIENT_ID,
        "client_secret": google.CLIENT_SECRET,
        "refresh_token": google.REFRESH,
    },
}
SYNCED = {"holidays", "football", "formula1", "ical", "ical_private", "enable_banking"}
SYNCED |= {"google_health", "prices"}
ASKED = {
    "food.search": {"query": "oat drink"},
    "books.search": {"query": "example novel"},
    "podcasts.search": {"query": "science"},
    "films.search": {"query": "example film"},
    "places.search": {"query": "Example Town"},
    "fx.rate": {"currency": "USD"},
    "weather.forecast": {"lat": 42.81, "lon": -1.64},
    "weather.climate": {"lat": 42.81, "lon": -1.64, "month": 7},
    "places.nearby": {"lat": 42.81, "lon": -1.64, "kind": "food"},
    "food.get": {"items": [{"source": "off", "source_ref": "8400000000017"}]},
    "books.cover": {"source": "openlibrary", "ref": "1"},
    "places.photo": {
        "name": "Example Town",
        "osm_ref": "relation/1000",
        "lat": 42.81,
        "lon": -1.64,
    },
    "routes.directions": {"points": [[42.81, -1.64], [42.95, -1.45]], "mode": "car"},
}


def test_fake_mode_swaps_a_provider_only_when_it_is_on(monkeypatch) -> None:
    real = types.ModuleType("weather")
    double = types.ModuleType("weather_fake")
    monkeypatch.setitem(fake.FAKES, "weather", double)

    monkeypatch.delenv(fake.MODE, raising=False)
    assert fake.provider("weather", real) is real
    assert capabilities.source_transport() is None

    monkeypatch.setenv(fake.MODE, "fake")
    assert fake.provider("weather", real) is double
    assert fake.provider("books", real) is real
    assert isinstance(capabilities.source_transport(), httpx.MockTransport)


@pytest.fixture
def offline(monkeypatch) -> list[str]:
    outbound: list[str] = []

    async def refuse(self, request: httpx.Request) -> httpx.Response:
        outbound.append(str(request.url))
        raise AssertionError(f"fake mode went out to {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)
    monkeypatch.setenv(fake.MODE, "fake")
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    fake.UNANSWERED.clear()
    doubles.stateful.cache_clear()
    return outbound


async def test_every_synced_source_answers_from_its_double_without_going_out(offline) -> None:
    got: dict[str, int] = {}
    async with httpx.AsyncClient(transport=capabilities.source_transport()) as client:
        for provider in catalogue.PROVIDERS:
            if provider.id not in SYNCED:
                continue
            connection = SimpleNamespace(
                id=uuid4(),
                provider=provider.id,
                label=provider.id,
                config=CONFIGS.get(provider.id, {}),
                last_ok=None,
                last_ok_at=None,
                state={},
            )
            assert provider.sync is not None
            found = await provider.sync.fetch(client, SECRETS.get(provider.id, {}), connection)
            got[provider.id] = len(getattr(found, "events", found))

    assert set(got) == SYNCED
    assert all(count > 0 for count in got.values()), got
    assert (offline, fake.UNANSWERED) == ([], [])


async def test_every_capability_answers_from_its_double_without_going_out(api, offline) -> None:
    for capability, body in ASKED.items():
        answer = await api.post(
            f"/capabilities/{capability}",
            json=body,
            headers={"x-module-token": TOKEN, "x-arga-module": "travel"},
        )
        assert answer.status_code == 200, (capability, answer.text)
        assert answer.json(), capability

    assert (offline, fake.UNANSWERED) == ([], [])


async def test_a_request_with_no_double_is_refused_and_named(offline) -> None:
    async with httpx.AsyncClient(transport=capabilities.source_transport()) as client:
        answer = await client.get("https://unknown.invalid/anything")

    assert answer.status_code == 503
    assert fake.UNANSWERED == ["GET unknown.invalid/anything"]
    assert offline == []
