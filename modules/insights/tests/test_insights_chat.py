from __future__ import annotations

import json

import httpx
import pytest
from insights_world import insight

from insights import talk

WRITE = {"x-arga-scopes": "insights:read insights:write"}


class FakeHub:
    def __init__(self, answer: dict | None = None, status: int = 200) -> None:
        self.asked: list[dict] = []
        self.answer = answer or {"outcome": "queued", "run": "r", "repeated": False}
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/capabilities/claude.run"
        assert request.headers["x-arga-module"] == "insights"
        self.asked.append(json.loads(request.content))
        return httpx.Response(self.status, json=self.answer)


@pytest.fixture
def hub(monkeypatch) -> FakeHub:
    fake = FakeHub()
    monkeypatch.setattr(talk, "transport", lambda: httpx.MockTransport(fake))
    return fake


async def test_saying_something_asks_your_claude_with_the_whole_thread(api, hub) -> None:
    await api.put("/profile", json={"name": "Txuri", "about": "I want to lower my cholesterol."})

    started = (await api.post("/threads", json={"text": "How is my spending this month?"})).json()

    assert started["waiting_since"] is not None
    assert [m["author"] for m in started["messages"]] == ["person"]
    (asked,) = hub.asked
    assert asked["key"] == f"thread:{started['messages'][0]['id']}"
    assert "tools" not in asked or asked["tools"] == []
    prompt = asked["prompt"]
    assert "You are Txuri" in prompt
    assert f'thread_id "{started["id"]}"' in prompt
    assert "I want to lower my cholesterol." in prompt
    assert prompt.rstrip().endswith("[Person] How is my spending this month?")


async def test_the_reply_arrives_through_the_tool_and_ends_the_wait(api, hub) -> None:
    started = (await api.post("/threads", json={"text": "Hola"})).json()

    replied = await api.post(
        "/tools/reply",
        json={"thread_id": started["id"], "text": "Hola. Gastas 2.097 €…"},
        headers=WRITE,
    )
    thread = (await api.get(f"/threads/{started['id']}")).json()

    assert replied.status_code == 200
    assert thread["waiting_since"] is None
    assert [(m["author"], m["body"]) for m in thread["messages"]] == [
        ("person", "Hola"),
        ("insights", "Hola. Gastas 2.097 €…"),
    ]


async def test_following_up_sends_what_was_said_before(api, hub) -> None:
    started = (await api.post("/threads", json={"text": "First"})).json()
    await api.post(
        "/tools/reply", json={"thread_id": started["id"], "text": "Answer"}, headers=WRITE
    )

    await api.post(f"/threads/{started['id']}/messages", json={"text": "Second"})

    prompt = hub.asked[-1]["prompt"]
    assert "[Person] First\n[Insights] Answer\n[Person] Second" in prompt


async def test_answering_an_insight_carries_it(api, hub) -> None:
    published = await api.post("/tools/publish_insight", json=insight(), headers=WRITE)
    insight_id = published.json()["content"]["published"]["insight_id"]

    started = (
        await api.post("/threads", json={"text": "And what do I do?", "insight_id": insight_id})
    ).json()

    assert started["title"] == "Restaurants, 60 % above your usual"
    assert "412 € against 258 (your 12-month average)" in hub.asked[-1]["prompt"]


async def test_without_permission_the_thread_says_where_to_give_it(api, monkeypatch) -> None:
    fake = FakeHub({"outcome": "skipped", "code": "not_granted"})
    monkeypatch.setattr(talk, "transport", lambda: httpx.MockTransport(fake))

    started = (await api.post("/threads", json={"text": "Hola"})).json()

    assert started["waiting_since"] is None
    assert "Allow it in Hub" in started["problem"]


async def test_asking_again_uses_a_new_key(api, monkeypatch) -> None:
    fake = FakeHub({"outcome": "skipped", "code": "not_granted"})
    monkeypatch.setattr(talk, "transport", lambda: httpx.MockTransport(fake))
    started = (await api.post("/threads", json={"text": "Hola"})).json()
    fake.answer = {"outcome": "queued"}

    again = (await api.post(f"/threads/{started['id']}/retry")).json()

    assert again["problem"] is None and again["waiting_since"] is not None
    assert fake.asked[0]["key"] != fake.asked[1]["key"]


async def test_a_reply_to_a_thread_that_is_not_yours_is_not_written(api, hub) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    answer = await api.post("/tools/reply", json={"thread_id": missing, "text": "x"}, headers=WRITE)

    assert answer.json()["content"]["replied"] is None


def test_the_day_is_written_out() -> None:
    from datetime import datetime

    assert talk.said_day(datetime(2026, 10, 8)) == "Thursday 8 October 2026"


async def ran(schema, key: str, outcome: str, code: str | None = None, detail: str | None = None):
    from datetime import UTC, datetime

    from sqlalchemy import text

    payload = {"operation": "run", "outcome": outcome, "code": code, "detail": detail, "key": key}
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash) "
                "values (:ts, 'hub', 'claude', 'hub.run', cast(:p as jsonb), :d)"
            ),
            {"ts": datetime.now(UTC), "p": json.dumps(payload), "d": f"run:{key}"},
        )


async def asked(api, hub) -> tuple[str, str]:
    started = (await api.post("/threads", json={"text": "How am I doing?"})).json()
    return started["id"], hub.asked[-1]["key"]


async def test_a_pass_that_failed_stops_the_wait_and_says_why(api, hub, schema) -> None:
    thread_id, key = await asked(api, hub)
    await ran(schema, f"insights:{key}", "error", detail="the MCP did not answer")

    thread = (await api.get(f"/threads/{thread_id}")).json()

    assert thread["waiting_since"] is None
    assert thread["problem"] == "It could not answer: the MCP did not answer"


async def test_the_usage_limit_is_said_as_such(api, hub, schema) -> None:
    thread_id, key = await asked(api, hub)
    await ran(schema, f"insights:{key}", "rate_limited")

    listed = (await api.get("/threads")).json()

    assert listed[0]["problem"].startswith("You reached your AI usage limit")


async def test_a_pass_that_ended_without_replying_says_so(api, hub, schema) -> None:
    thread_id, key = await asked(api, hub)
    await ran(schema, f"insights:{key}", "ok")

    thread = (await api.get(f"/threads/{thread_id}")).json()

    assert thread["problem"] == "It finished without answering. Ask again."


async def test_a_pass_that_replied_leaves_nothing_to_say(api, hub, schema) -> None:
    thread_id, key = await asked(api, hub)
    await api.post("/tools/reply", json={"thread_id": thread_id, "text": "Bien."}, headers=WRITE)
    await ran(schema, f"insights:{key}", "ok")

    thread = (await api.get(f"/threads/{thread_id}")).json()

    assert thread["problem"] is None and thread["waiting_since"] is None


async def test_another_questions_pass_does_not_count(api, hub, schema) -> None:
    thread_id, _ = await asked(api, hub)
    await ran(
        schema, "insights:thread:00000000-0000-4000-8000-000000000000", "error", detail="another"
    )

    thread = (await api.get(f"/threads/{thread_id}")).json()

    assert thread["waiting_since"] is not None and thread["problem"] is None


async def test_a_conversation_is_deleted_with_its_messages(api, hub) -> None:
    thread_id, _ = await asked(api, hub)

    assert (await api.delete(f"/threads/{thread_id}")).status_code == 204
    assert (await api.get(f"/threads/{thread_id}")).status_code == 404
    assert (await api.delete(f"/threads/{thread_id}")).status_code == 404
    assert (await api.get("/threads")).json() == []
