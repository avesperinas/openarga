import json
from pathlib import Path

import httpx
import httpx2
import pytest

from hub.ai.providers import (
    Anthropic,
    OpenAICompatible,
    ProviderError,
    ToolResult,
    ToolSpec,
    strict_schema,
)

RECORDED = Path(__file__).parent / "fixtures" / "ai"
SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "day": {"type": "string"}},
            },
        },
        "page": {"type": "string"},
    },
}
TOOL = ToolSpec(
    "training_get_sessions",
    "Training sessions of the last days.",
    {"type": "object", "properties": {"days": {"type": "integer"}}},
)


def recorded(name: str) -> dict:
    return json.loads((RECORDED / f"{name}.json").read_text())


class Seen(list):
    def answer(self, *bodies: dict, status: int = 200):
        queue = list(bodies)

        def handle(request):
            self.append(request)
            return (status, queue.pop(0) if len(queue) > 1 else queue[0])

        return handle


def anthropic_with(seen: Seen, *bodies: dict, status: int = 200, base_url=None) -> Anthropic:
    handle = seen.answer(*bodies, status=status)

    def reply(request: httpx2.Request) -> httpx2.Response:
        code, body = handle(request)
        return httpx2.Response(code, json=body)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(reply))
    provider = Anthropic("sk-ant-synthetic-key", base_url, client)
    provider.client = provider.client.with_options(max_retries=0)
    return provider


def openai_with(seen: Seen, *bodies: dict, statuses=None) -> OpenAICompatible:
    codes = list(statuses or [])
    handle = seen.answer(*bodies)

    def reply(request: httpx.Request) -> httpx.Response:
        code, body = handle(request)
        return httpx.Response(codes.pop(0) if codes else code, json=body)

    return OpenAICompatible(
        "http://ollama.local:11434/v1/",
        None,
        httpx.AsyncClient(transport=httpx.MockTransport(reply)),
    )


def sent(request) -> dict:
    return json.loads(request.content)


async def test_anthropic_extracts_with_structured_output_and_no_forced_tool() -> None:
    seen = Seen()
    provider = anthropic_with(seen, recorded("anthropic_extract"))

    answer = await provider.extract(
        "claude-haiku-5-5", "fast", "List the events.", "Jazz night on Friday.", SCHEMA
    )

    assert answer.output == {
        "events": [{"title": "Jazz night", "day": "2026-11-20"}],
        "page": "Agenda",
    }
    assert (answer.usage.input_tokens, answer.usage.output_tokens) == (412, 38)
    request = seen[0]
    body = sent(request)
    assert request.url.path == "/v1/messages"
    assert "anthropic-version" in request.headers
    assert "sk-ant-synthetic-key" in (
        request.headers.get("authorization", "") + request.headers.get("x-api-key", "")
    )
    assert body["model"] == "claude-haiku-5-5"
    assert body["system"] == "List the events."
    assert "tool_choice" not in body and "temperature" not in body
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"] == {
        "type": "json_schema",
        "schema": strict_schema(SCHEMA),
    }


async def test_anthropic_asks_for_refusal_fallbacks_only_where_they_exist() -> None:
    seen = Seen()
    first_party = anthropic_with(seen, recorded("anthropic_extract"))
    await first_party.extract("claude-opus-5-5", "smart", "x", "y", SCHEMA)
    await first_party.extract("claude-haiku-5-5", "fast", "x", "y", SCHEMA)
    proxied = anthropic_with(seen, recorded("anthropic_extract"), base_url="http://proxy.local")
    await proxied.extract("claude-opus-5-5", "smart", "x", "y", SCHEMA)

    assert sent(seen[0])["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen[0].headers.get("anthropic-beta", "")
    assert "fallbacks" not in sent(seen[1])
    assert "fallbacks" not in sent(seen[2])


async def test_anthropic_says_when_the_model_declines() -> None:
    provider = anthropic_with(Seen(), recorded("anthropic_refusal"))
    with pytest.raises(ProviderError, match="declined"):
        await provider.extract("claude-haiku-5-5", "fast", "x", "y", SCHEMA)


@pytest.mark.parametrize(
    ("status", "retryable", "said"),
    [(401, False, "key"), (429, True, "rate"), (529, True, "failed"), (400, False, "rejected")],
)
async def test_anthropic_errors_say_whether_to_try_again(status, retryable, said) -> None:
    error = {"type": "error", "error": {"type": "x", "message": "synthetic"}}
    provider = anthropic_with(Seen(), error, status=status)
    with pytest.raises(ProviderError, match=said) as raised:
        await provider.extract("claude-haiku-5-5", "fast", "x", "y", SCHEMA)
    assert raised.value.retryable is retryable


async def test_anthropic_tool_loop_keeps_the_assistant_turn_whole() -> None:
    seen = Seen()
    provider = anthropic_with(seen, recorded("anthropic_tool_use"), recorded("anthropic_extract"))
    conversation = provider.conversation("claude-opus-5-5", "smart", "Be brief.", "Week?", [TOOL])

    turn = await conversation.step()
    assert turn.stop == "tools"
    assert [(call.name, call.arguments) for call in turn.calls] == [
        ("training_get_sessions", {"days": 7})
    ]
    conversation.answer([ToolResult(turn.calls[0], "3 sessions", error=False)])
    await conversation.step()

    second = sent(seen[1])
    assert second["tools"][0]["name"] == "training_get_sessions"
    assistant = second["messages"][1]
    assert [block["type"] for block in assistant["content"]] == ["thinking", "text", "tool_use"]
    assert second["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_01synthetic", "content": "3 sessions"}
    ]


async def test_openai_compatible_extracts_from_fenced_json() -> None:
    seen = Seen()
    provider = openai_with(seen, recorded("openai_extract"))

    answer = await provider.extract("llama3.3", "fast", "List the events.", "Jazz.", SCHEMA)

    assert answer.output["page"] == "Agenda"
    assert (answer.usage.input_tokens, answer.usage.output_tokens) == (380, 41)
    body = sent(seen[0])
    assert str(seen[0].url) == "http://ollama.local:11434/v1/chat/completions"
    assert "authorization" not in seen[0].headers
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA


async def test_openai_compatible_falls_back_to_json_mode() -> None:
    seen = Seen()
    rejected = {"error": {"message": "response_format json_schema is not supported"}}
    provider = openai_with(seen, rejected, recorded("openai_extract"), statuses=[400, 200])

    answer = await provider.extract("llama3.3", "fast", "List the events.", "Jazz.", SCHEMA)

    assert answer.output["events"][0]["title"] == "Jazz night"
    retry = sent(seen[1])
    assert retry["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in retry["messages"][0]["content"]


async def test_openai_compatible_tool_loop() -> None:
    seen = Seen()
    provider = openai_with(seen, recorded("openai_tool_call"), recorded("openai_extract"))
    conversation = provider.conversation("gpt-5", "smart", "Be brief.", "Week?", [TOOL])

    turn = await conversation.step()
    assert turn.calls[0].arguments == {"days": 7}
    conversation.answer([ToolResult(turn.calls[0], "nothing found", error=True)])
    await conversation.step()

    second = sent(seen[1])
    assert second["tools"][0]["function"]["parameters"] == TOOL.schema
    assert second["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "call_synthetic",
        "content": "Error: nothing found",
    }
