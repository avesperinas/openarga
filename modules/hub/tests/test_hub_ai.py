import json
from pathlib import Path

import httpx
import pytest
from conftest import OTHER, PERSON
from sqlalchemy import text

from arga_tenancy import USER_HEADER, as_user
from hub import ai
from hub.capabilities import CAPABILITIES
from hub.connections import Refused
from hub.db import as_module

RECORDED = Path(__file__).parent / "fixtures" / "ai"
SCHEMA = {
    "type": "object",
    "properties": {"events": {"type": "array"}, "page": {"type": "string"}},
    "required": ["events", "page"],
}
ASK = {
    "instructions": "List the events on the page.",
    "input": "Jazz on Friday.",
    "output_schema": SCHEMA,
}


@pytest.fixture(autouse=True)
def instance(monkeypatch):
    for name in ("PROVIDER", "BASE_URL", "FAST_MODEL", "SMART_MODEL", "MONTHLY_TOKENS", "KEY"):
        monkeypatch.delenv(f"OPENARGA_AI_{name}", raising=False)
    monkeypatch.delenv("CONNECTIONS_MODE", raising=False)


@pytest.fixture
async def clean(schema):
    async with schema.begin() as connection:
        await connection.execute(text("delete from hub.ai_attempt"))
        await connection.execute(text("delete from hub.ai_settings"))
    yield


def ollama(monkeypatch, body: dict | None = None) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    answer = body or json.loads((RECORDED / "openai_extract.json").read_text())

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer)

    monkeypatch.setattr(ai, "source_transport", lambda: httpx.MockTransport(reply))
    return seen


async def attempts() -> list:
    async with as_module() as connection:
        return (await connection.execute(text("select * from hub.ai_attempt"))).all()


async def test_extract_answers_with_the_shape_asked_for_in_fake_mode(clean, monkeypatch) -> None:
    monkeypatch.setenv("CONNECTIONS_MODE", "fake")
    answer = await ai.extract("outings", ASK)

    assert answer["output"] == {"events": [], "page": ""}
    assert answer["provider"] == "fake"
    [logged] = await attempts()
    assert (logged.app, logged.capability, logged.status) == ("outings", "extract", "done")


async def test_without_a_provider_extract_says_so(clean) -> None:
    with pytest.raises(Refused, match="no AI provider") as refused:
        await ai.extract("outings", ASK)
    assert refused.value.status == 503


async def test_a_wrong_schema_is_refused_before_asking_anyone(clean, monkeypatch) -> None:
    monkeypatch.setenv("CONNECTIONS_MODE", "fake")
    with pytest.raises(Refused, match="not a JSON Schema"):
        await ai.extract("outings", {**ASK, "output_schema": {"type": "thing"}})
    assert await attempts() == []


async def test_an_openai_compatible_endpoint_answers_and_the_tokens_are_logged(
    clean, monkeypatch
) -> None:
    monkeypatch.setenv("OPENARGA_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENARGA_AI_BASE_URL", "http://ollama.local:11434/v1")
    monkeypatch.setenv("OPENARGA_AI_FAST_MODEL", "llama3.3")
    seen = ollama(monkeypatch)

    answer = await ai.extract("outings", ASK)

    assert answer["output"]["page"] == "Agenda"
    assert (answer["provider"], answer["model"]) == ("openai", "llama3.3")
    assert json.loads(seen[0].content)["model"] == "llama3.3"
    [logged] = await attempts()
    assert (logged.input_tokens, logged.output_tokens, logged.status) == (380, 41, "done")


async def test_an_answer_outside_the_schema_fails_and_says_why(clean, monkeypatch) -> None:
    monkeypatch.setenv("OPENARGA_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENARGA_AI_BASE_URL", "http://ollama.local:11434/v1")
    monkeypatch.setenv("OPENARGA_AI_FAST_MODEL", "llama3.3")
    wrong = {
        "choices": [{"message": {"content": '{"page": 3}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }
    ollama(monkeypatch, wrong)

    with pytest.raises(Refused, match="does not match") as refused:
        await ai.extract("outings", ASK)

    assert refused.value.status == 502
    [logged] = await attempts()
    assert (logged.status, logged.input_tokens) == ("failed", 10)


async def test_the_budget_cuts_when_the_month_is_spent(clean, monkeypatch) -> None:
    monkeypatch.setenv("CONNECTIONS_MODE", "fake")
    async with as_module() as connection:
        await connection.execute(text("insert into hub.ai_settings (monthly_tokens) values (1000)"))
        await connection.execute(
            text(
                "insert into hub.ai_attempt (app, capability, role, provider, model, status, "
                "input_tokens, output_tokens) "
                "values ('insights', 'run', 'smart', 'fake', 'fake', 'done', 900, 100)"
            )
        )

    with pytest.raises(Refused, match="budget") as refused:
        await ai.extract("outings", ASK)

    assert refused.value.status == 429
    statuses = sorted(row.status for row in await attempts())
    assert statuses == ["done", "over_budget"]


async def test_settings_are_each_persons_and_the_key_never_comes_back(clean, api) -> None:
    alex = {USER_HEADER: str(PERSON)}
    sam = {USER_HEADER: str(OTHER)}
    saved = await api.put(
        "/ai/settings",
        json={
            "provider": "anthropic",
            "smart_model": "claude-opus-5-5",
            "monthly_tokens": 2_000_000,
        },
        headers=alex,
    )
    assert saved.status_code == 200, saved.text
    assert (
        await api.put("/ai/key", json={"key": "sk-ant-synthetic-0123456789"}, headers=alex)
    ).status_code == 204

    mine = (await api.get("/ai/settings", headers=alex)).json()
    theirs = (await api.get("/ai/settings", headers=sam)).json()

    assert mine["provider"] == "anthropic"
    assert mine["fast_model"] is None and mine["smart_model"] == "claude-opus-5-5"
    assert mine["own_key"] is True and mine["key_hint"]
    assert "sk-ant-synthetic-0123456789" not in json.dumps(mine)
    assert theirs["provider"] == "none" and theirs["own_key"] is False

    with as_user(PERSON):
        async with as_module() as connection:
            from hub.ai import settings

            found = await settings.effective(connection)
    assert found.key == "sk-ant-synthetic-0123456789"
    assert found.model("fast") == "claude-haiku-5-5"

    assert (await api.delete("/ai/key", headers=alex)).status_code == 204
    assert (await api.get("/ai/settings", headers=alex)).json()["own_key"] is False


async def test_each_person_sees_only_their_own_attempts(clean, api, monkeypatch) -> None:
    monkeypatch.setenv("CONNECTIONS_MODE", "fake")
    with as_user(PERSON):
        await ai.extract("outings", ASK)

    alex = (await api.get("/ai/attempts", headers={USER_HEADER: str(PERSON)})).json()
    sam = (await api.get("/ai/attempts", headers={USER_HEADER: str(OTHER)})).json()

    assert [one["app"] for one in alex["attempts"]] == ["outings"]
    assert sam["attempts"] == [] and sam["spent"] == 0


def test_both_are_capabilities_of_the_hub() -> None:
    assert {"ai.extract", "ai.run"} <= set(CAPABILITIES)
