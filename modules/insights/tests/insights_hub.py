from __future__ import annotations

import json

import httpx

from insights import hub, runs


class FakeHub:
    def __init__(self, refuse: int | None = None) -> None:
        self.asked: list[dict] = []
        self.ended: dict[str, dict] = {}
        self.refuse = refuse

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["x-arga-module"] == "insights"
        body = json.loads(request.content)
        if request.url.path == "/internal/capabilities/ai.status":
            return httpx.Response(200, json=self.ended.get(body["key"], {"status": "queued"}))
        assert request.url.path == "/internal/capabilities/ai.run"
        self.asked.append(body)
        if self.refuse:
            return httpx.Response(self.refuse, json={"detail": "refused by the hub"})
        return httpx.Response(200, json={"status": "queued", "run_id": "r"})

    def end(self, key: str, status: str, detail: str | None = None, **extra: str) -> None:
        self.ended[key] = {"status": status, "detail": detail, **extra}


def install(monkeypatch, fake: FakeHub) -> FakeHub:
    monkeypatch.setattr(hub, "transport", lambda: httpx.MockTransport(fake))
    return fake


async def settle() -> int:
    from insights.main import as_role

    async with as_role("mod_insights") as connection:
        return await runs.settle(connection)
