from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx

from arga_module.publisher import Publisher

ALEX = uuid4()
SAM = uuid4()


class Connection:
    def __init__(self, rows: list) -> None:
        self.rows = rows
        self.done: list[list] = []
        self.failed: list = []

    async def execute(self, statement, values=None):
        sql = str(statement)
        if "limit :batch" in sql:
            return SimpleNamespace(all=lambda: self.rows)
        if "any(:ids)" in sql:
            self.done.append(list(values["ids"]))
        elif "last_error = :error" in sql:
            self.failed.append(values["id"])
        elif "published_at = now()" in sql:
            self.done.append([values["id"]])
        return None


def row(number: int, owner) -> SimpleNamespace:
    return SimpleNamespace(
        id=number,
        type="probe.metric",
        ts=datetime(2026, 11, 21, tzinfo=UTC),
        payload={"n": number},
        dedup_hash=f"probe:{number}",
        user_id=owner,
    )


def kernel(batch_status: int = 200):
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/events/batch":
            return httpx.Response(batch_status, json={"results": []})
        return httpx.Response(200, json={})

    return seen, httpx.AsyncClient(transport=httpx.MockTransport(answer))


def publisher(monkeypatch) -> Publisher:
    monkeypatch.setenv("KERNEL_URL", "http://kernel")
    return Publisher("probe", lambda: None)


async def test_one_person_s_batch_goes_in_one_request(monkeypatch) -> None:
    connection = Connection([row(1, ALEX), row(2, ALEX), row(3, ALEX)])
    seen, client = kernel()

    result = await publisher(monkeypatch).publish_pending(connection, client)

    assert seen == ["/events/batch"]
    assert connection.done == [[1, 2, 3]]
    assert result == {"published": 3, "pending": 0}


async def test_a_refused_batch_goes_one_by_one(monkeypatch) -> None:
    connection = Connection([row(1, ALEX), row(2, ALEX)])
    seen, client = kernel(batch_status=422)

    result = await publisher(monkeypatch).publish_pending(connection, client)

    assert seen == ["/events/batch", "/events", "/events"]
    assert connection.done == [[1], [2]]
    assert result["published"] == 2


async def test_rows_of_different_people_go_one_by_one(monkeypatch) -> None:
    connection = Connection([row(1, ALEX), row(2, SAM)])
    seen, client = kernel()

    await publisher(monkeypatch).publish_pending(connection, client)

    assert seen == ["/events", "/events"]
    assert connection.done == [[1], [2]]
