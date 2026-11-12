from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx

from arga_tenancy import current_user
from hub import sync, worker


def movement(n: int) -> dict:
    return {
        "ts": "2026-10-01T00:00:00+00:00",
        "type": "finance.movement",
        "payload": {
            "account": "a",
            "reference": f"r{n}",
            "booked_on": "2026-10-01",
            "amount": "-1.00",
            "currency": "EUR",
        },
        "dedup_hash": f"m:{n}",
    }


def kernel_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://kernel")


async def test_a_pass_publishes_in_batches_and_counts_what_was_new() -> None:
    calls: list[tuple[str, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        events = json.loads(request.content)["events"]
        calls.append((request.url.path, len(events)))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"id": str(uuid4()), "dedup_hash": e["dedup_hash"], "created": n % 2 == 1}
                    for n, e in enumerate(events)
                ]
            },
        )

    result = sync.Outcome(UUID(int=0), "ok")
    async with kernel_with(handler) as kernel:
        new = await sync.publish_all(
            kernel, "enable_banking", [movement(n) for n in range(450)], result
        )

    assert calls == [("/events/batch", 200), ("/events/batch", 200), ("/events/batch", 50)]
    assert (result.emitted, result.duplicated) == (225, 225)
    assert new == 225


async def test_a_kernel_without_the_batch_gets_them_one_by_one() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/events/batch":
            return httpx.Response(404)
        return httpx.Response(200, json={"id": str(uuid4()), "dedup_hash": "x", "created": True})

    result = sync.Outcome(UUID(int=0), "ok")
    async with kernel_with(handler) as kernel:
        await sync.publish_all(kernel, "enable_banking", [movement(n) for n in range(3)], result)

    assert paths == ["/events/batch", "/events", "/events", "/events"]
    assert result.emitted == 3


async def test_the_worker_runs_passes_at_once_up_to_its_limit(monkeypatch) -> None:
    people = [uuid4(), uuid4(), uuid4()]
    running = 0
    most = 0
    seen: dict[str, UUID | None] = {}

    async def runnable(moment, everything):
        user = current_user.get()
        return [SimpleNamespace(id=uuid4(), label=f"{user}-{n}") for n in range(3)]

    async def run(connection, **_):
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.01)
        seen[connection.label] = current_user.get()
        running -= 1
        return SimpleNamespace(outcome="ok")

    async def refresh(*_):
        return None

    monkeypatch.setattr(worker, "runnable", runnable)
    monkeypatch.setattr(worker.sync, "run", run)
    monkeypatch.setattr(worker.avisos, "refresh", refresh)
    monkeypatch.setattr(worker.capabilities, "maps_recheck", refresh)
    monkeypatch.setattr(worker, "beat", lambda: None)
    monkeypatch.setattr(worker, "CONCURRENCY", 4)

    async def everyone() -> list[UUID]:
        return people

    done = await worker.tick(datetime.now(UTC), True, people=everyone, source=None, kernel=None)  # type: ignore[arg-type]

    assert most == 4
    assert list(done) == [str(user) for user in people]
    assert all(len(labels) == 3 for labels in done.values())
    assert all(label.startswith(str(user)) for label, user in seen.items())


async def test_a_pass_that_breaks_does_not_stop_the_others(monkeypatch) -> None:
    async def runnable(moment, everything):
        return [SimpleNamespace(id=uuid4(), label=label) for label in ("rota", "buena")]

    async def run(connection, **_):
        if connection.label == "rota":
            raise RuntimeError("se rompió")
        await asyncio.sleep(0.01)
        return SimpleNamespace(outcome="ok")

    async def refresh(*_):
        return None

    monkeypatch.setattr(worker, "runnable", runnable)
    monkeypatch.setattr(worker.sync, "run", run)
    monkeypatch.setattr(worker.avisos, "refresh", refresh)
    monkeypatch.setattr(worker.capabilities, "maps_recheck", refresh)
    monkeypatch.setattr(worker, "beat", lambda: None)
    person = uuid4()

    async def everyone() -> list[UUID]:
        return [person]

    done = await worker.tick(datetime.now(UTC), True, people=everyone, source=None, kernel=None)  # type: ignore[arg-type]

    assert done == {str(person): {"buena": "ok"}}
