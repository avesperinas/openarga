from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import capabilities, db, sync, worker
from hub.providers import claude

TOKEN = f"sk-ant-oat01-{secrets.token_hex(12)}"
MODULE_TOKEN = secrets.token_hex(16)


class FakeAnthropic:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.status = 200
        self.resets_at = datetime.now(UTC) + timedelta(hours=4)
        self.week_used = "0.4"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        headers = {
            "anthropic-ratelimit-unified-5h-reset": str(int(self.resets_at.timestamp())),
            "anthropic-ratelimit-unified-5h-utilization": "0.12",
            "anthropic-ratelimit-unified-7d-reset": str(int(self.resets_at.timestamp()) + 86400),
            "anthropic-ratelimit-unified-7d-utilization": self.week_used,
        }
        if self.status != 200:
            return httpx.Response(
                self.status,
                headers=headers,
                json={"error": {"type": "rate_limit_error", "message": "Límite alcanzado"}},
            )
        return httpx.Response(
            200, headers=headers, json={"content": [{"text": "o"}], "model": "claude-haiku-4-5"}
        )


@pytest.fixture
def fake() -> FakeAnthropic:
    return FakeAnthropic()


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

    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", MODULE_TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    clean = text("delete from kernel.events where module = 'hub'")
    async with kernel_db.engine().begin() as connection:
        await connection.execute(clean)
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(clean)
    await kernel_db.engine().dispose()


def ask(api, capability: str, body: dict):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": MODULE_TOKEN, "x-arga-module": "chuping"},
    )


async def hand_over(api, account: UUID, token: str | None = TOKEN, label: str = "Principal"):
    response = await ask(
        api,
        "claude.handoff",
        {"connection": str(account), "label": label, "secrets": {"token": token} if token else {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def events(schema, event_type: str) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select payload, dedup_hash from kernel.events "
                    "where module = 'hub' and type = :type order by ts"
                ),
                {"type": event_type},
            )
        ).all()


async def test_an_account_arrives_with_its_own_id_and_its_token(api, kernel) -> None:
    account = uuid4()

    first = await hand_over(api, account)
    again = await hand_over(api, account, token=f"sk-ant-oat01-{secrets.token_hex(12)}")

    assert first == {"connection": str(account), "created": True}
    assert again == {"connection": str(account), "created": False}
    ficha = (await api.get(f"/connections/{account}")).json()
    assert (ficha["provider"], ficha["label"], ficha["state"]) == ("claude", "Principal", "active")
    assert ficha["secrets"][0]["hint"] == f"…{TOKEN[-4:]}"


async def test_an_account_without_a_token_is_there_but_half_done(api, kernel) -> None:
    account = uuid4()

    await hand_over(api, account, token=None, label="Trabajo")

    ficha = (await api.get(f"/connections/{account}")).json()
    assert ficha["state"] == "pending"
    assert ficha["reason"] == "A Trabajo le falta su credencial: pégala en su ficha."
    pasted = await api.put(f"/connections/{account}/credentials/token", json={"value": TOKEN})
    assert pasted.json()["state"] == "active"


async def test_the_same_ping_is_launched_once_even_across_a_restart(
    api, kernel, schema, fake
) -> None:
    account = uuid4()
    await hand_over(api, account)
    ping = {"connection": str(account), "key": "scheduled:2026-09-22T09:00", "trigger": "scheduled"}

    first = await ask(api, "claude.ping", ping)
    await db.engine().dispose()
    db.engine.cache_clear()
    again = await ask(api, "claude.ping", ping)

    assert first.json()["outcome"] == "ok"
    assert again.json() == {"outcome": "ok", "detail": None, "repeated": True}
    assert len(fake.calls) == 1
    assert json.loads(fake.calls[0].content)["model"] == "claude-haiku-4-5"
    [published] = await events(schema, "ai.claude.ping")
    assert published.dedup_hash == "pings:scheduled:2026-09-22T09:00"
    assert published.payload["account_id"] == str(account)
    assert published.payload["trigger"] == "scheduled"
    assert published.payload["window_utilization"] == 12.0
    ficha = (await api.get(f"/connections/{account}")).json()
    assert [(r["operation"], r["outcome"], r["emitted"]) for r in ficha["runs"]] == [
        ("ping", "ok", 1)
    ]


async def test_without_a_token_anthropic_is_not_called_and_the_run_says_why(
    api, kernel, schema, fake
) -> None:
    account = uuid4()
    await hand_over(api, account, token=None)

    answer = await ask(
        api, "claude.ping", {"connection": str(account), "key": "manual:1", "trigger": "manual"}
    )

    assert answer.json()["outcome"] == "skipped"
    assert answer.json()["code"] == sync.MISSING_CREDENTIAL
    assert fake.calls == []
    [run] = await events(schema, "hub.run")
    assert (run.payload["operation"], run.payload["code"]) == ("ping", "missing_credential")


async def test_a_429_is_published_and_is_not_a_failure(api, kernel, schema, fake) -> None:
    account = uuid4()
    await hand_over(api, account)
    fake.status = 429

    answer = await ask(
        api, "claude.ping", {"connection": str(account), "key": "manual:2", "trigger": "manual"}
    )

    assert answer.json()["outcome"] == "rate_limited"
    [published] = await events(schema, "ai.claude.ping")
    assert published.payload["success"] is False
    assert published.payload["status_code"] == 429
    assert (await api.get(f"/connections/{account}")).json()["state"] == "active"


async def test_a_paused_account_launches_nothing(api, kernel, fake) -> None:
    account = uuid4()
    await hand_over(api, account)
    await api.post(f"/connections/{account}/pause")

    answer = await ask(
        api, "claude.ping", {"connection": str(account), "key": "manual:3", "trigger": "manual"}
    )

    assert answer.json()["outcome"] == "skipped"
    assert fake.calls == []


async def test_an_account_that_is_not_here_is_a_404(api, kernel) -> None:
    answer = await ask(
        api, "claude.ping", {"connection": str(uuid4()), "key": "manual:4", "trigger": "manual"}
    )

    assert answer.status_code == 404


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def observed(minutes_ago: int, resets_in: timedelta | None, success: bool = True):
    payload = {
        "success": success,
        "window_resets_at": (NOW + resets_in).isoformat() if resets_in is not None else None,
    }
    return NOW - timedelta(minutes=minutes_ago), payload


@pytest.mark.parametrize(
    ("observation", "due"),
    [
        (observed(6, timedelta(hours=3)), True),
        (observed(1, timedelta(hours=3)), False),
        (observed(30, timedelta(minutes=-1)), False),
        (observed(30, None), False),
        (observed(30, timedelta(minutes=2)), False),
        (observed(30, timedelta(hours=3), success=False), False),
        ((None, None), False),
    ],
)
def test_usage_is_read_only_with_the_window_open(observation, due) -> None:
    assert claude.usage_due(*observation, NOW) is due


async def test_after_a_ping_the_worker_reads_the_usage_and_only_then(
    api, kernel, schema, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    account = uuid4()
    await hand_over(api, account)

    async def people() -> list[UUID]:
        return [person]

    async def tick(at: datetime) -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as source:
            return await worker.tick(at, True, people=people, source=source, kernel=kernel)

    now = datetime.now(UTC)
    before = await tick(now)
    await ask(
        api, "claude.ping", {"connection": str(account), "key": "manual:5", "trigger": "manual"}
    )
    right_after = await tick(now + timedelta(minutes=1))
    later = await tick(now + timedelta(minutes=6))

    assert before == {}
    assert right_after == {}
    assert later == {str(person): {"Principal": "ok"}}
    assert len(fake.calls) == 2
    [usage] = await events(schema, "ai.claude.usage")
    assert usage.payload["account_id"] == str(account)
    assert usage.dedup_hash.startswith(f"pings:usage:{account}:")


async def test_every_change_is_told_so_an_app_can_say_what_is_missing(api, kernel, schema) -> None:
    account = uuid4()
    await hand_over(api, account, token=None)
    await api.put(f"/connections/{account}/credentials/token", json={"value": TOKEN})
    await api.post(f"/connections/{account}/pause")
    await api.delete(f"/connections/{account}")

    told = [row.payload for row in await events(schema, "hub.connection")]

    assert [(t["state"], t["missing"], t["paused"], t["removed"]) for t in told] == [
        ("pending", ["token"], False, False),
        ("active", [], False, False),
        ("paused", [], True, False),
        ("removed", [], True, True),
    ]
    assert all(TOKEN not in str(t) for t in told)
