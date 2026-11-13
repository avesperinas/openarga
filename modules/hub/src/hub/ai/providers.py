from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import anthropic
import httpx
import httpx2

ANTHROPIC_MODELS = {"fast": "claude-haiku-5-5", "smart": "claude-opus-5-5"}
# Server-side refusal fallbacks exist for these families on the first-party API only.
FALLBACK_FAMILIES = ("claude-opus-", "claude-sonnet-", "claude-fable-")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000
EFFORT = {"fast": "low", "smart": "high"}


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call: ToolCall
    content: str
    error: bool = False


@dataclass
class Turn:
    stop: Literal["done", "tools", "refused", "truncated"]
    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class Extracted:
    output: Any
    usage: Usage


class Conversation(Protocol):
    async def step(self) -> Turn: ...

    def answer(self, results: list[ToolResult]) -> None: ...


class Provider(Protocol):
    name: str

    async def extract(
        self, model: str, role: str, instructions: str, text: str, schema: dict[str, Any]
    ) -> Extracted: ...

    def conversation(
        self, model: str, role: str, system: str, task: str, tools: list[ToolSpec]
    ) -> Conversation: ...


def strict_schema(schema: Any) -> Any:
    """Structured outputs need closed objects with every property required."""
    if isinstance(schema, list):
        return [strict_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    found = {key: strict_schema(value) for key, value in schema.items()}
    if found.get("type") == "object" and isinstance(found.get("properties"), dict):
        found["additionalProperties"] = False
        found["required"] = list(found["properties"])
    return found


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_json(text: str) -> Any:
    try:
        return json.loads(FENCE.sub("", text.strip()))
    except json.JSONDecodeError as error:
        raise ProviderError(f"the model did not answer with JSON: {error.msg}") from error


def _anthropic_error(error: Exception) -> ProviderError:
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return ProviderError("the provider refused the key")
    if isinstance(error, anthropic.RateLimitError):
        return ProviderError("the provider is rate limiting this key", retryable=True)
    if isinstance(error, anthropic.APIStatusError):
        if error.status_code >= 500:
            return ProviderError(f"the provider failed ({error.status_code})", retryable=True)
        return ProviderError(f"the provider rejected the request: {error.message}")
    if isinstance(error, anthropic.APIConnectionError):
        return ProviderError("the provider is not reachable", retryable=True)
    return ProviderError(f"{type(error).__name__}: {error}")


class Anthropic:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.first_party = base_url is None
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            max_retries=2,
            timeout=600.0,
        )

    def _fallbacks(self, model: str) -> dict[str, Any]:
        if self.first_party and model.startswith(FALLBACK_FAMILIES):
            return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        return {}

    async def create(self, model: str, **params: Any) -> Any:
        extra = self._fallbacks(model)
        try:
            if extra:
                return await self.client.beta.messages.create(model=model, **params, **extra)
            return await self.client.messages.create(model=model, **params)
        except anthropic.AnthropicError as error:
            raise _anthropic_error(error) from error

    async def extract(
        self, model: str, role: str, instructions: str, text: str, schema: dict[str, Any]
    ) -> Extracted:
        response = await self.create(
            model,
            max_tokens=MAX_TOKENS,
            system=instructions,
            messages=[{"role": "user", "content": text}],
            output_config={
                "effort": EFFORT.get(role, "low"),
                "format": {"type": "json_schema", "schema": strict_schema(schema)},
            },
        )
        usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            raise ProviderError("the model declined the request")
        if response.stop_reason == "max_tokens":
            raise ProviderError("the answer did not fit")
        answer = next((block.text for block in response.content if block.type == "text"), "")
        return Extracted(parse_json(answer), usage)

    def conversation(
        self, model: str, role: str, system: str, task: str, tools: list[ToolSpec]
    ) -> AnthropicConversation:
        return AnthropicConversation(self, model, role, system, task, tools)


class AnthropicConversation:
    def __init__(
        self,
        provider: Anthropic,
        model: str,
        role: str,
        system: str,
        task: str,
        tools: list[ToolSpec],
    ) -> None:
        self.provider = provider
        self.model = model
        self.role = role
        self.system = system
        self.tools = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.schema}
            for tool in tools
        ]
        self.messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    async def step(self) -> Turn:
        response = await self.provider.create(
            self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
            output_config={"effort": EFFORT.get(self.role, "high")},
        )
        usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
        # The assistant content goes back untouched: thinking blocks must survive the loop.
        self.messages.append({"role": "assistant", "content": response.content})
        text = "\n".join(block.text for block in response.content if block.type == "text")
        calls = [
            ToolCall(block.id, block.name, dict(block.input))
            for block in response.content
            if block.type == "tool_use"
        ]
        if response.stop_reason == "refusal":
            return Turn("refused", text, [], usage)
        if response.stop_reason == "max_tokens":
            return Turn("truncated", text, [], usage)
        if response.stop_reason == "pause_turn":
            return Turn("tools", text, [], usage)
        return Turn("tools" if calls else "done", text, calls, usage)

    def answer(self, results: list[ToolResult]) -> None:
        if not results:
            return
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": result.call.id,
                        "content": result.content,
                        **({"is_error": True} if result.error else {}),
                    }
                    for result in results
                ],
            }
        )


class OpenAICompatible:
    name = "openai"

    def __init__(self, base_url: str, api_key: str | None, client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=600.0
            )
        except httpx.HTTPError as error:
            raise ProviderError("the provider is not reachable", retryable=True) from error
        if response.status_code in (401, 403):
            raise ProviderError("the provider refused the key")
        if response.status_code == 429:
            raise ProviderError("the provider is rate limiting this key", retryable=True)
        if response.status_code >= 500:
            raise ProviderError(f"the provider failed ({response.status_code})", retryable=True)
        if response.status_code >= 400:
            raise ProviderError(f"the provider rejected the request ({response.status_code})")
        try:
            return response.json()
        except ValueError as error:
            raise ProviderError("the provider did not answer with JSON") from error

    @staticmethod
    def usage_of(body: dict[str, Any]) -> Usage:
        found = body.get("usage") or {}
        return Usage(int(found.get("prompt_tokens") or 0), int(found.get("completion_tokens") or 0))

    @staticmethod
    def message_of(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        try:
            choice = body["choices"][0]
            return choice["message"], choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("the provider answered without a message") from error

    async def extract(
        self, model: str, role: str, instructions: str, text: str, schema: dict[str, Any]
    ) -> Extracted:
        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": text},
        ]
        try:
            body = await self.chat(
                {
                    "model": model,
                    "messages": messages,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "answer", "schema": schema},
                    },
                }
            )
        except ProviderError as error:
            if error.retryable or "rejected" not in str(error):
                raise
            # Endpoints without JSON schema support still honour JSON mode.
            schema_note = (
                f"\n\nAnswer with JSON only, matching this JSON Schema:\n{json.dumps(schema)}"
            )
            messages[0] = {"role": "system", "content": instructions + schema_note}
            body = await self.chat(
                {"model": model, "messages": messages, "response_format": {"type": "json_object"}}
            )
        message, finish = self.message_of(body)
        if finish == "length":
            raise ProviderError("the answer did not fit")
        return Extracted(parse_json(message.get("content") or ""), self.usage_of(body))

    def conversation(
        self, model: str, role: str, system: str, task: str, tools: list[ToolSpec]
    ) -> OpenAIConversation:
        return OpenAIConversation(self, model, system, task, tools)


class OpenAIConversation:
    def __init__(
        self,
        provider: OpenAICompatible,
        model: str,
        system: str,
        task: str,
        tools: list[ToolSpec],
    ) -> None:
        self.provider = provider
        self.model = model
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.schema,
                },
            }
            for tool in tools
        ]
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]

    async def step(self) -> Turn:
        body = {"model": self.model, "messages": self.messages}
        if self.tools:
            body["tools"] = self.tools
        answer = await self.provider.chat(body)
        message, finish = self.provider.message_of(answer)
        usage = self.provider.usage_of(answer)
        self.messages.append({key: value for key, value in message.items() if value is not None})
        calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                ToolCall(
                    str(call.get("id")),
                    str(function.get("name")),
                    arguments if isinstance(arguments, dict) else {},
                )
            )
        text = message.get("content") or ""
        if finish == "length":
            return Turn("truncated", text, [], usage)
        if finish == "content_filter":
            return Turn("refused", text, [], usage)
        return Turn("tools" if calls else "done", text, calls, usage)

    def answer(self, results: list[ToolResult]) -> None:
        for result in results:
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.call.id,
                    "content": f"Error: {result.content}" if result.error else result.content,
                }
            )


def empty_of(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "object":
        return {name: empty_of(sub) for name, sub in (schema.get("properties") or {}).items()}
    if kind == "array":
        return []
    if kind in ("integer", "number"):
        return 0
    if kind == "boolean":
        return False
    if kind == "string":
        return ""
    return None


class Fake:
    """Answers without a model: empty shapes for extraction, a run that does nothing."""

    name = "fake"

    async def extract(
        self, model: str, role: str, instructions: str, text: str, schema: dict[str, Any]
    ) -> Extracted:
        return Extracted(empty_of(schema), Usage())

    def conversation(
        self, model: str, role: str, system: str, task: str, tools: list[ToolSpec]
    ) -> FakeConversation:
        return FakeConversation()


class FakeConversation:
    async def step(self) -> Turn:
        return Turn(
            "done", "The fake AI provider did nothing. Configure a provider in Connections."
        )

    def answer(self, results: list[ToolResult]) -> None:
        return None
