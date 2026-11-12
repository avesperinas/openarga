from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_contracts import sources
from hub import sync, worker
from hub.providers import bitvavo

KEY = secrets.token_hex(16)
SECRET = secrets.token_hex(32)
TOKEN = secrets.token_hex(16)


class FakeBitvavo:
    def __init__(self) -> None:
        self.holdings = [
            {"symbol": "BTC", "available": "0.10000000", "inOrder": "0.02500000"},
            {"symbol": "EUR", "available": "250.40", "inOrder": "0"},
        ]
        self.failures: list[int] = []
        self.private_calls = 0
        self.history: list[list[dict]] = [[]]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode().removeprefix("/v2")
        if path == "/ticker/price":
            return httpx.Response(200, json=[{"market": "BTC-EUR", "price": "40000"}])
        if path == "/balance":
            self.private_calls += 1
            if self.failures:
                status = self.failures.pop(0)
                return httpx.Response(
                    status, json={"errorCode": 305, "error": "No active API key."}
                )
            timestamp = request.headers["bitvavo-access-timestamp"]
            expected = hmac.new(
                SECRET.encode(), f"{timestamp}GET/v2/balance".encode(), hashlib.sha256
            ).hexdigest()
            assert request.headers["bitvavo-access-key"] == KEY
            assert request.headers["bitvavo-access-signature"] == expected
            return httpx.Response(200, json=self.holdings)
        if path.startswith("/account/history?"):
            timestamp = request.headers["bitvavo-access-timestamp"]
            expected = hmac.new(
                SECRET.encode(), f"{timestamp}GET/v2{path}".encode(), hashlib.sha256
            ).hexdigest()
            assert request.headers["bitvavo-access-signature"] == expected
            page = int(request.url.params["page"])
            return httpx.Response(
                200,
                json={
                    "items": self.history[page - 1],
                    "currentPage": page,
                    "totalPages": len(self.history),
                    "maxItems": 100,
                },
            )
        return httpx.Response(404, json={"errorCode": 110, "error": path})


@pytest.fixture
def fake() -> FakeBitvavo:
    return FakeBitvavo()


@pytest.fixture
async def source(fake):
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as client:
        yield client


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    await kernel_db.engine().dispose()


async def connect(api, **extra) -> dict:
    response = await api.post(
        "/connections",
        json={"provider": "bitvavo", "secrets": {"api_key": KEY, "api_secret": SECRET}, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def pass_of(connection: dict, source, kernel, **options) -> sync.Outcome:
    async def no_wait(_: float) -> None:
        return None

    row = SimpleNamespace(id=UUID(connection["id"]), provider="bitvavo", label=connection["label"])
    return await sync.run(row, source=source, kernel=kernel, sleep=no_wait, **options)


async def published(schema, event_type: str) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select module, source, type, payload, dedup_hash from kernel.events "
                    "where module = 'hub' and type = :type order by dedup_hash"
                ),
                {"type": event_type},
            )
        ).all()


async def test_connecting_bitvavo_keeps_the_key_and_never_gives_it_back(api) -> None:
    connection = await connect(api)

    ficha = await api.get(f"/connections/{connection['id']}")

    assert ficha.status_code == 200
    body = ficha.json()
    assert body["label"] == "Bitvavo"
    assert body["state"] == "active"
    assert [(s["key"], s["configured"]) for s in body["secrets"]] == [
        ("api_key", True),
        ("api_secret", True),
    ]
    assert body["secrets"][0]["hint"] == f"…{KEY[-4:]}"
    assert KEY not in ficha.text and SECRET not in ficha.text
    assert body["runs"] == []


async def test_bitvavo_is_one_per_person(api) -> None:
    await connect(api)

    again = await api.post(
        "/connections",
        json={"provider": "bitvavo", "secrets": {"api_key": KEY, "api_secret": SECRET}},
    )

    assert again.status_code == 409
    assert "Ya tienes Bitvavo" in again.json()["detail"]


async def test_what_arga_does_not_know_is_not_connected(api) -> None:
    unknown = await api.post("/connections", json={"provider": "nadie", "secrets": {}})

    assert unknown.status_code == 404


@pytest.mark.parametrize(
    ("secrets_in", "said"),
    [
        ({"api_key": KEY}, "Falta secreto"),
        ({"api_key": "no es una clave", "api_secret": SECRET}, "Clave de API"),
        ({"api_key": KEY, "api_secret": SECRET, "otra": "x"}, "no pide otra"),
    ],
)
async def test_what_is_pasted_has_to_be_what_it_asks_for(api, secrets_in, said) -> None:
    response = await api.post("/connections", json={"provider": "bitvavo", "secrets": secrets_in})

    assert response.status_code == 422
    assert said in response.json()["detail"]


async def test_changing_the_key_changes_what_it_ends_in(api) -> None:
    connection = await connect(api)
    other = secrets.token_hex(16)

    response = await api.put(
        f"/connections/{connection['id']}/credentials/api_key", json={"value": f"  {other} "}
    )

    assert response.status_code == 200, response.text
    assert response.json()["secrets"][0]["hint"] == f"…{other[-4:]}"
    assert (
        await api.put(f"/connections/{connection['id']}/credentials/otra", json={"value": other})
    ).status_code == 404


async def test_paused_resumed_and_removed(api) -> None:
    connection = await connect(api)

    paused = (await api.post(f"/connections/{connection['id']}/pause")).json()
    resumed = (await api.post(f"/connections/{connection['id']}/resume")).json()
    removed = await api.delete(f"/connections/{connection['id']}")

    assert (paused["state"], paused["paused"]) == ("paused", True)
    assert (resumed["state"], resumed["paused"]) == ("active", False)
    assert removed.status_code == 204
    assert (await api.get(f"/connections/{connection['id']}")).status_code == 404
    assert (await api.get("/connections")).json() == []


async def test_a_pass_publishes_with_the_identity_money_used(api, schema, kernel, source) -> None:
    connection = await connect(api)
    today = datetime.now(UTC).date().isoformat()

    outcome = await pass_of(connection, source, kernel)

    assert (outcome.outcome, outcome.emitted, outcome.detail) == ("ok", 4, None)
    [announced] = await published(schema, "finance.account")
    balances = await published(schema, "finance.balance")
    holdings = await published(schema, "finance.holding")
    assert (announced.dedup_hash, announced.payload["bank"]) == ("bitvavo:account", "Bitvavo")
    assert announced.payload["account"] == balances[0].payload["account"] == "bitvavo"
    assert [(e.source, e.dedup_hash) for e in balances] == [
        ("bitvavo", f"exchange:bitvavo:{today}")
    ]
    assert balances[0].payload["amount"] == "5250.40"
    assert [e.dedup_hash for e in holdings] == [
        f"exchange:bitvavo:BTC:{today}",
        f"exchange:bitvavo:EUR:{today}",
    ]
    [run] = await published(schema, "hub.run")
    assert run.payload["connection"] == connection["id"]
    assert (run.payload["outcome"], run.payload["emitted"]) == ("ok", 4)

    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    assert [(r["outcome"], r["emitted"]) for r in ficha["runs"]] == [("ok", 4)]
    assert ficha["last_ok_at"] is not None


async def test_the_same_day_twice_is_one_valuation(api, schema, kernel, source) -> None:
    connection = await connect(api)

    await pass_of(connection, source, kernel)
    second = await pass_of(connection, source, kernel)

    assert (second.outcome, second.emitted, second.duplicated) == ("ok", 0, 4)
    assert len(await published(schema, "finance.balance")) == 1
    assert len(await published(schema, "finance.account")) == 1


async def test_what_bitvavo_says_when_it_refuses_is_kept_in_its_words(
    api, schema, kernel, source, fake
) -> None:
    connection = await connect(api)
    fake.failures = [403, 403]

    await pass_of(connection, source, kernel)
    outcome = await pass_of(connection, source, kernel)

    assert outcome.outcome == "error"
    assert "No active API key" in outcome.detail
    assert await published(schema, "finance.balance") == []
    ficha = (await api.get(f"/connections/{connection['id']}")).json()
    assert ficha["state"] == "failing"
    assert "No active API key" in ficha["reason"]
    assert fake.private_calls == 2


async def test_a_429_is_not_a_failure_and_is_not_retried(api, kernel, source, fake) -> None:
    connection = await connect(api)
    fake.failures = [429]

    outcome = await pass_of(connection, source, kernel)

    assert outcome.outcome == "rate_limited"
    assert fake.private_calls == 1
    assert (await api.get(f"/connections/{connection['id']}")).json()["state"] == "active"


async def test_what_is_passing_is_retried(api, kernel, source, fake) -> None:
    connection = await connect(api)
    fake.failures = [502, 503]

    outcome = await pass_of(connection, source, kernel, attempts=3)

    assert (outcome.outcome, outcome.emitted) == ("ok", 4)
    assert fake.private_calls == 3


def test_its_identity_is_the_one_money_used() -> None:
    from decimal import Decimal

    day = datetime(2026, 9, 22, tzinfo=UTC).date()
    holdings = {"BTC": Decimal("0.125"), "EUR": Decimal("250.40")}
    prices = {"BTC": Decimal("40000")}

    hub = bitvavo.events(holdings, prices, day)

    assert [(e["type"], e["dedup_hash"]) for e in hub] == [
        ("finance.holding", "exchange:bitvavo:BTC:2026-09-22"),
        ("finance.holding", "exchange:bitvavo:EUR:2026-09-22"),
        ("finance.balance", "exchange:bitvavo:2026-09-22"),
    ]
    assert hub[0]["payload"] == {
        "account": "bitvavo",
        "symbol": "BTC",
        "on": "2026-09-22",
        "quantity": "0.125",
        "price": "40000",
        "value": "5000.00",
    }
    assert hub[2]["payload"]["amount"] == "5250.40"


def row(provider: str = "bitvavo", ran: bool = True) -> SimpleNamespace:
    return SimpleNamespace(id=UUID(int=1), provider=provider, label="x", ran=ran)


@pytest.mark.parametrize(
    ("moment", "everything", "rows", "expected"),
    [
        ("2026-09-22T05:00", False, [row()], 1),
        ("2026-09-22T05:01", False, [row()], 0),
        ("2026-09-22T12:00", True, [row()], 1),
        ("2026-09-22T12:00", False, [row(ran=False)], 1),
        ("2026-09-22T05:00", True, [row("usda")], 0),
    ],
)
def test_what_is_due(moment, everything, rows, expected) -> None:
    at = datetime.fromisoformat(moment).replace(tzinfo=UTC)

    assert len(worker.due(rows, at, everything)) == expected


async def test_the_worker_runs_a_new_connection_and_leaves_a_paused_one(
    api, schema, kernel, source, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    connection = await connect(api)

    async def people() -> list[UUID]:
        return [person]

    async def no_wait(_: float) -> None:
        return None

    noon = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    first = await worker.tick(
        noon, False, people=people, source=source, kernel=kernel, sleep=no_wait
    )
    again = await worker.tick(
        noon, False, people=people, source=source, kernel=kernel, sleep=no_wait
    )
    await api.post(f"/connections/{connection['id']}/pause")
    paused = await worker.tick(
        noon, True, people=people, source=source, kernel=kernel, sleep=no_wait
    )

    assert first == {str(person): {"Bitvavo": "ok"}}
    assert again == {}
    assert paused == {}
    assert (tmp_path / "alive").exists()


async def test_only_the_kernel_asks_for_a_handoff(api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    body = {"secrets": {"api_key": KEY, "api_secret": SECRET}}

    without = await api.post("/capabilities/bitvavo.handoff", json=body)
    wrong = await api.post(
        "/capabilities/bitvavo.handoff", json=body, headers={"x-module-token": "otro"}
    )
    unknown = await api.post(
        "/capabilities/nada.que.ver", json=body, headers={"x-module-token": TOKEN}
    )

    assert (without.status_code, wrong.status_code, unknown.status_code) == (401, 401, 404)
    assert (await api.get("/connections")).json() == []


async def test_a_handoff_is_idempotent_and_never_overwrites(api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    headers = {"x-module-token": TOKEN, "x-arga-module": "money"}

    first = await api.post(
        "/capabilities/bitvavo.handoff",
        json={"label": "Bitvavo", "secrets": {"api_key": KEY, "api_secret": SECRET}},
        headers=headers,
    )
    second = await api.post(
        "/capabilities/bitvavo.handoff",
        json={"secrets": {"api_key": secrets.token_hex(16), "api_secret": SECRET}},
        headers=headers,
    )

    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert second.json() == {"connection": first.json()["connection"], "created": False}
    ficha = (await api.get(f"/connections/{first.json()['connection']}")).json()
    assert ficha["secrets"][0]["hint"] == f"…{KEY[-4:]}"


def moved(id_: str, kind: str, sent: tuple[str, str] | None, got: tuple[str, str] | None, **extra):
    return {
        "transactionId": id_,
        "executedAt": "2026-03-01T10:00:00.000Z",
        "type": kind,
        "sentCurrency": sent[0] if sent else None,
        "sentAmount": sent[1] if sent else None,
        "receivedCurrency": got[0] if got else None,
        "receivedAmount": got[1] if got else None,
        "feesCurrency": "EUR",
        "feesAmount": "0",
        **extra,
    }


def test_the_history_becomes_trades_read_by_what_comes_in_and_goes_out() -> None:
    found = bitvavo.trades(
        [
            moved("a", "deposit", ("EUR", "1000"), None),
            moved("b", "buy", ("EUR", "500"), ("BTC", "0.01"), feesAmount="1.25"),
            moved("c", "sell", ("BTC", "0.004"), ("EUR", "240")),
            moved(
                "d",
                "buy",
                ("BTC", "0.002"),
                ("ETH", "0.05"),
                priceCurrency="EUR",
                priceAmount="2400",
            ),
            moved("e", "staking", None, ("ETH", "0.001")),
            moved("f", "withdrawal", ("ETH", "0.01"), None),
            moved("g", "withdrawal_cancelled", None, ("ETH", "0.01")),
        ]
    )
    shown = [
        (
            one["payload"]["id"],
            one["payload"]["side"],
            one["payload"]["symbol"],
            one["payload"]["quantity"],
            one["payload"]["price"],
            one["payload"]["fee"],
        )
        for one in found
    ]
    assert shown == [
        ("b", "buy", "BTC", "0.01", "50000", "1.25"),
        ("c", "sell", "BTC", "0.004", "60000", None),
        ("d:sell", "sell", "BTC", "0.002", "60000", None),
        ("d:buy", "buy", "ETH", "0.05", "2400", None),
        ("e", "in", "ETH", "0.001", None, None),
        ("f", "out", "ETH", "0.01", None, None),
    ]
    assert found[2]["payload"]["group"] == found[3]["payload"]["group"] == "d"
    assert len({one["dedup_hash"] for one in found}) == len(found)
    for one in found:
        sources.check(one["type"], one["payload"])


async def test_a_pass_reads_every_page_of_the_history(fake, source) -> None:
    fake.history = [
        [moved("b", "buy", ("EUR", "500"), ("BTC", "0.01"))],
        [moved("c", "sell", ("BTC", "0.004"), ("EUR", "240"))],
    ]
    found = await bitvavo.sync(source, {"api_key": KEY, "api_secret": SECRET})
    assert [one["payload"]["id"] for one in found if one["type"] == "finance.trade"] == ["b", "c"]
