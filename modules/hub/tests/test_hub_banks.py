from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx
import pytest
from bank_fake import ACCOUNT, APP_ID, BANK, IBAN, OTHER_IBAN, PEM, FakeEnableBanking
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import banks, capabilities, worker

APP = {"app_id": APP_ID, "private_key": PEM}


@pytest.fixture
def fake() -> FakeEnableBanking:
    return FakeEnableBanking()


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, fake, monkeypatch):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    await forget(kernel_db)
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    await forget(kernel_db)
    await kernel_db.engine().dispose()


async def forget(kernel_db) -> None:
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
        await connection.execute(
            text("update kernel.entities set merged_into = null where module = 'hub'")
        )
        await connection.execute(text("delete from kernel.entities where module = 'hub'"))


async def connect(api, fake, **extra) -> UUID:
    started = await api.post(
        "/connections", json={"provider": "enable_banking", "bank": BANK, **extra}
    )
    assert started.status_code == 201, started.text
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["s"][0]
    back = await api.get(f"/hub/callback?state={state}&code=codigo-sintetico")
    assert back.status_code == 303, back.text
    return UUID(started.json()["id"])


async def events(schema, event_type: str) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select source, payload, dedup_hash from kernel.events "
                    "where module = 'hub' and type = :type order by dedup_hash"
                ),
                {"type": event_type},
            )
        ).all()


async def tick(kernel, fake, person, at: datetime) -> dict:
    async def people() -> list[UUID]:
        return [person]

    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as source:
        return await worker.tick(at, False, people=people, source=source, kernel=kernel)


async def test_connecting_a_bank_goes_to_it_and_comes_back_active(api, kernel, schema, fake):
    before = (await api.get("/providers/enable_banking")).json()
    listed = await api.post("/providers/enable_banking/banks", json={"secrets": APP})

    connection = await connect(api, fake, secrets=APP)

    assert before["app"] is False
    assert listed.json() == [BANK]
    ficha = (await api.get(f"/connections/{connection}")).json()
    assert (ficha["label"], ficha["state"], ficha["authorizes"]) == (BANK, "active", True)
    assert datetime.fromisoformat(ficha["consent_expires_at"]) == fake.valid_until
    assert ficha["accounts"] == [{"name": "Cuenta nómina", "iban_tail": "1234", "kind": "checking"}]
    assert ficha["budget"] == {"limit": 4, "used": 0, "remaining": 4}
    [account] = await events(schema, "finance.account")
    assert (account.source, account.payload["bank"], account.payload["account"]) == (
        "bank",
        BANK,
        ACCOUNT,
    )
    assert PEM not in str(ficha)


async def test_the_app_is_pasted_once_and_the_next_bank_takes_it(api, kernel, fake) -> None:
    first = await connect(api, fake, secrets=APP)

    second = await connect(api, fake, label="Otro banco")

    assert (await api.get("/providers/enable_banking")).json()["app"] is True
    hints = [
        [s["hint"] for s in (await api.get(f"/connections/{c}")).json()["secrets"]]
        for c in (first, second)
    ]
    assert hints[0] == hints[1]


async def test_without_the_app_it_is_asked_for(api, kernel) -> None:
    listed = await api.post("/providers/enable_banking/banks", json={})

    assert listed.status_code == 422
    assert "aplicación de Enable Banking" in listed.json()["detail"]


async def test_an_app_without_this_return_address_says_which_one_to_add(api, kernel, fake) -> None:
    fake.refusal = (400, "REDIRECT_URI_NOT_ALLOWED")

    started = await api.post(
        "/connections", json={"provider": "enable_banking", "bank": BANK, "secrets": APP}
    )

    assert started.status_code == 409
    assert banks.redirect_url() in started.json()["detail"]
    assert (await api.get("/connections")).json() == []


async def test_what_the_bank_refuses_is_never_a_502_or_504_that_cloudflare_swallows(
    api, kernel, fake
) -> None:
    fake.refusal = (500, "ASPSP_ERROR")
    down = await api.post(
        "/connections", json={"provider": "enable_banking", "bank": BANK, "secrets": APP}
    )
    fake.refusal = (400, "WRONG_ASPSP_PROVIDED")
    wrong = await api.post(
        "/connections", json={"provider": "enable_banking", "bank": BANK, "secrets": APP}
    )

    assert (down.status_code, wrong.status_code) == (503, 409)
    assert "ASPSP_ERROR" in down.json()["detail"]
    assert "WRONG_ASPSP_PROVIDED" in wrong.json()["detail"]


async def test_a_bank_that_gives_no_account_says_so_until_it_is_reconnected(
    api, kernel, fake
) -> None:
    fake.no_accounts = True
    started = await api.post(
        "/connections", json={"provider": "enable_banking", "bank": BANK, "secrets": APP}
    )
    connection = started.json()["id"]
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["s"][0]
    back = await api.get(f"/hub/callback?state={state}&code=codigo-sintetico")
    empty = (await api.get(f"/connections/{connection}")).json()

    fake.no_accounts = False
    again = await api.post(f"/connections/{connection}/reauthorize")
    state = parse_qs(urlparse(again.json()["authorization_url"]).query)["s"][0]
    fixed = await api.get(f"/hub/callback?state={state}&code=otro-codigo")
    ficha = (await api.get(f"/connections/{connection}")).json()

    assert back.headers["location"] == f"/hub/{connection}?banco=sin-cuentas"
    assert (empty["state"], empty["tone"]) == ("failing", "negative")
    assert "enlaza en su panel las cuentas de este banco" in empty["reason"]
    assert fixed.headers["location"] == f"/hub/{connection}?banco=conectado"
    assert (ficha["state"], ficha["reason"], len(ficha["accounts"])) == ("active", None, 1)


async def test_a_return_nobody_asked_for_or_cancelled_says_so(api, kernel) -> None:
    unknown = await api.get("/hub/callback?state=inventado&code=x")
    cancelled = await api.get("/hub/callback?error=access_denied")

    assert unknown.headers["location"] == "/hub/?banco=desconocido"
    assert cancelled.headers["location"] == "/hub/?banco=cancelado"


async def test_a_new_bank_syncs_in_the_minute_and_then_waits_for_its_hour(
    api, kernel, schema, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    connection = await connect(api, fake, secrets=APP)
    now = datetime.now(UTC).replace(second=0, microsecond=0)

    first = await tick(kernel, fake, person, now)
    after = await tick(kernel, fake, person, now + timedelta(minutes=1))

    assert first == {str(person): {BANK: "ok"}}
    assert after == {}
    assert fake.account_calls == 1
    movements = await events(schema, "finance.movement")
    assert [(m.source, m.dedup_hash) for m in movements] == [
        ("bank", f"bank:{ACCOUNT}:REF-001"),
        ("bank", f"bank:{ACCOUNT}:TX-777"),
    ]
    [balance] = await events(schema, "finance.balance")
    assert balance.dedup_hash == f"bank:{ACCOUNT}:2026-09-20"
    ficha = (await api.get(f"/connections/{connection}")).json()
    assert ficha["runs"][0]["detail"] == "1 apuntes sin identidad del banco"
    assert ficha["budget"]["remaining"] == 3


async def test_never_more_than_four_accesses_a_day(api, kernel, fake) -> None:
    connection = await connect(api, fake, secrets=APP)

    answers = [await api.post(f"/connections/{connection}/sync") for _ in range(5)]

    assert [a.status_code for a in answers] == [200, 200, 200, 200, 409]
    assert [a.json()["budget"]["remaining"] for a in answers[:4]] == [3, 2, 1, 0]
    assert "no quedan accesos" in answers[4].json()["detail"]
    assert fake.account_calls == 4


async def test_a_consent_the_bank_ends_leaves_it_expired_without_retrying(
    api, kernel, fake
) -> None:
    connection = await connect(api, fake, secrets=APP)
    fake.failure = (401, "EXPIRED_SESSION")

    answer = (await api.post(f"/connections/{connection}/sync")).json()

    assert answer["outcome"] == "error"
    assert "EXPIRED_SESSION" in answer["outcome_detail"]
    assert answer["state"] == "expired"
    assert "hay que reconectarlo" in answer["reason"]
    assert fake.account_calls == 1


async def test_reconnecting_is_the_same_connection_with_a_new_consent(api, kernel, fake) -> None:
    connection = await connect(api, fake, secrets=APP)
    fake.valid_until += timedelta(days=30)

    again = await api.post(f"/connections/{connection}/reauthorize")
    state = parse_qs(urlparse(again.json()["authorization_url"]).query)["s"][0]
    back = await api.get(f"/hub/callback?state={state}&code=otro-codigo")

    assert back.headers["location"] == f"/hub/{connection}?banco=conectado"
    ficha = (await api.get(f"/connections/{connection}")).json()
    assert datetime.fromisoformat(ficha["consent_expires_at"]) == fake.valid_until
    assert len((await api.get("/connections")).json()) == 1


async def test_changing_the_app_key_changes_it_in_every_bank(api, kernel, fake) -> None:
    first = await connect(api, fake, secrets=APP)
    second = await connect(api, fake, label="Otro banco")

    await api.put(f"/connections/{first}/credentials/app_id", json={"value": str(UUID(int=7))})

    hints = [
        (await api.get(f"/connections/{c}")).json()["secrets"][0]["hint"] for c in (first, second)
    ]
    assert hints == ["…0007", "…0007"]


def test_a_transfer_says_the_account_on_the_other_side() -> None:
    from hub.providers import enable_banking as eb

    account = {"key": "hash-cuenta", "name": "Cuenta"}
    out = eb.movement_event(
        account,
        {
            "entry_reference": "REF-9",
            "transaction_amount": {"amount": "500.00", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "booking_date": "2026-09-20",
            "creditor": {"name": "TITULAR SINTETICO"},
            "creditor_account": {"iban": "es00 9999 0000 0000 0000 4321"},
        },
    )
    back = eb.movement_event(
        account,
        {
            "entry_reference": "REF-10",
            "transaction_amount": {"amount": "100.00", "currency": "EUR"},
            "credit_debit_indicator": "CRDT",
            "booking_date": "2026-09-21",
            "debtor_account": {"iban": "ES0099990000000000004321"},
        },
    )
    plain = eb.movement_event(
        account,
        {
            "entry_reference": "REF-11",
            "transaction_amount": {"amount": "3.00", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "booking_date": "2026-09-21",
        },
    )

    assert out["payload"]["counterparty_iban"] == "ES0099990000000000004321"
    assert back["payload"]["counterparty_iban"] == "ES0099990000000000004321"
    assert plain["payload"]["counterparty_iban"] is None


async def test_the_account_has_its_iban_and_each_entry_the_other_side(
    api, kernel, schema, fake, person
) -> None:
    await connect(api, fake, secrets=APP)

    await tick(kernel, fake, person, datetime.now(UTC).replace(second=0, microsecond=0))

    [account] = await events(schema, "finance.account")
    assert account.payload["iban"] == IBAN
    assert account.payload["iban_tail"] == IBAN[-4:]
    details = {
        d.payload["reference"]: d.payload for d in await events(schema, "finance.movement_detail")
    }
    assert details["REF-001"]["counterparty_iban"] == OTHER_IBAN
    assert details["REF-001"]["bank_transaction_code"] == {
        "code": "ICDT",
        "sub_code": "ESCT",
        "description": None,
    }
    assert details["TX-777"]["counterparty_name"] == "EMPRESA SINTETICA SL"
    assert details["TX-777"]["counterparty_iban"] is None
    assert [d.dedup_hash for d in await events(schema, "finance.movement_detail")] == [
        f"bank:{ACCOUNT}:REF-001:detail",
        f"bank:{ACCOUNT}:TX-777:detail",
    ]


async def test_a_bank_from_before_learns_its_iban_and_brings_the_year_once(
    api, kernel, schema, fake, person
) -> None:
    connection = await connect(api, fake, secrets=APP)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    await tick(kernel, fake, person, now)
    async with schema.begin() as database:
        await database.execute(
            text(
                "update hub.hub_connection set config = jsonb_set("
                "config - 'details_from', '{accounts,0}', "
                "(config->'accounts'->0) - 'iban') where id = :id"
            ),
            {"id": connection},
        )
        await database.execute(text("delete from kernel.events where type = 'finance.account'"))
    fake.calls.clear()
    fake.since.clear()

    slot = now.replace(hour=now.hour // 6 * 6, minute=0) + timedelta(hours=6)
    await tick(kernel, fake, person, slot + timedelta(hours=6))
    await tick(kernel, fake, person, slot + timedelta(hours=12))

    assert sum(call.endswith("/details") for call in fake.calls) == 1
    [account] = await events(schema, "finance.account")
    assert account.payload["iban"] == IBAN
    today = datetime.now(UTC).date()
    assert [date.fromisoformat(day) for day in fake.since] == [
        today - timedelta(days=365),
        today - timedelta(days=10),
    ]
