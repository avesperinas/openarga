import json

import httpx
import pytest
from conftest import OTHER, PERSON
from sqlalchemy import text

from arga_tenancy import as_user
from hub import ai
from hub.ai import runs as ai_run
from hub.ai.providers import Fake, ToolCall, Turn, Usage
from hub.ai.tools import Refused, Web, public_host
from hub.connections import Refused as Declined
from hub.db import as_module

TOOLS = [
    {
        "module": "training",
        "name": "get_sessions",
        "scope": "training:read",
        "description": "Sessions.",
    },
    {"module": "training", "name": "log_session", "scope": "training:write", "description": "Log."},
    {"module": "outings", "name": "save_event", "scope": "outings:write", "description": "Save."},
]
SCHEMAS = {
    "training": [
        {"name": "get_sessions", "input_schema": {"type": "object", "properties": {}}},
        {"name": "log_session", "input_schema": {"type": "object", "properties": {}}},
    ],
    "outings": [{"name": "save_event", "input_schema": {"type": "object", "properties": {}}}],
}


@pytest.fixture(autouse=True)
def fake_mode(monkeypatch):
    for name in ("PROVIDER", "BASE_URL", "FAST_MODEL", "SMART_MODEL", "MONTHLY_TOKENS", "KEY"):
        monkeypatch.delenv(f"OPENARGA_AI_{name}", raising=False)
    monkeypatch.setenv("OPENARGA_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENARGA_AI_BASE_URL", "http://model.internal/v1")
    monkeypatch.setenv("OPENARGA_AI_SMART_MODEL", "scripted")
    monkeypatch.setenv("MODULE_URL_TEMPLATE", "http://{module}.internal")


@pytest.fixture
async def clean(schema):
    async with schema.begin() as connection:
        await connection.execute(text("delete from hub.ai_attempt"))
        await connection.execute(text("delete from hub.ai_settings"))
    yield


class Stack:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host == "kernel.internal" and path == "/internal/users":
            return httpx.Response(200, json=[{"id": str(PERSON), "spaces": []}])
        if host == "kernel.internal" and path == "/tools":
            return httpx.Response(200, json=TOOLS)
        module = host.removesuffix(".internal")
        if path == "/tools":
            return httpx.Response(200, json=SCHEMAS[module])
        self.calls.append(request)
        return httpx.Response(200, json={"content": {"sessions": 3, "module": module}})

    def clients(self) -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
        transport = httpx.MockTransport(self.handle)
        return (
            httpx.AsyncClient(base_url="http://kernel.internal", transport=transport),
            httpx.AsyncClient(transport=transport),
        )


class Scripted(Fake):
    """The fake provider, told what to call: one read, one write, then a summary."""

    def __init__(self, tokens_per_step: int = 10) -> None:
        self.tokens = tokens_per_step
        self.seen_tools: list[str] = []
        self.results: list[str] = []

    def conversation(self, model, role, system, task, tools):
        self.seen_tools = [tool.name for tool in tools]
        script = iter(
            [
                [ToolCall("1", "training_get_sessions", {})],
                [ToolCall("2", "outings_save_event", {"title": "Jazz"})],
                [],
            ]
        )
        outer = self

        class Talk:
            async def step(self):
                calls = next(script)
                usage = Usage(outer.tokens, 0)
                if calls:
                    return Turn("tools", "", calls, usage)
                return Turn("done", "Saved one event after looking at 3 sessions.", [], usage)

            def answer(self, results):
                outer.results.extend(result.content for result in results)

        return Talk()


ASK = {"task": "Find this week's plans.", "key": "agenda:2026-W46", "web": False}


async def attempts():
    async with as_module() as connection:
        return (await connection.execute(text("select * from hub.ai_attempt"))).all()


async def test_a_run_is_queued_then_done_with_the_apps_tools(clean) -> None:
    queued = await ai.run("outings", ASK)
    assert queued["status"] == "queued" and queued["model"] == "scripted"

    stack, provider = Stack(), Scripted()
    kernel, modules = stack.clients()
    async with kernel, modules:
        assert await ai_run.drain(kernel, modules, providers=lambda _: provider) == 1

    assert provider.seen_tools == ["training_get_sessions", "outings_save_event"]
    [read, write] = stack.calls
    assert read.url.path == "/tools/get_sessions" and write.url.host == "outings.internal"
    scopes = set(write.headers["x-arga-scopes"].split())
    assert scopes == {"training:read", "outings:read", "outings:write"}
    assert write.headers["x-arga-user"] == str(PERSON)
    assert json.loads(provider.results[0])["sessions"] == 3

    [done] = await attempts()
    assert (done.status, done.steps, done.input_tokens) == ("done", 3, 30)
    assert done.summary.startswith("Saved one event")


async def test_the_same_key_is_not_run_twice(clean) -> None:
    first = await ai.run("outings", ASK)
    again = await ai.run("outings", ASK)
    other_app = await ai.run("insights", ASK)

    assert again["status"] == "repeated" and again["run_id"] == first["run_id"]
    assert other_app["status"] == "queued"


async def test_the_budget_cuts_a_run_in_the_middle(clean) -> None:
    async with as_module() as connection:
        await connection.execute(text("insert into hub.ai_settings (monthly_tokens) values (15)"))
    await ai.run("outings", ASK)

    stack, provider = Stack(), Scripted(tokens_per_step=10)
    kernel, modules = stack.clients()
    async with kernel, modules:
        await ai_run.drain(kernel, modules, providers=lambda _: provider)

    [cut] = await attempts()
    assert (cut.status, cut.steps) == ("over_budget", 2)
    assert "budget" in cut.detail
    assert len(stack.calls) == 1

    with pytest.raises(Declined) as refused:
        await ai.run("outings", {**ASK, "key": "agenda:2026-W47"})
    assert refused.value.status == 429


async def test_the_fake_provider_finishes_at_once_without_touching_anything(
    clean, monkeypatch
) -> None:
    monkeypatch.setenv("OPENARGA_AI_PROVIDER", "fake")
    answer = await ai.run("outings", ASK)
    again = await ai.run("outings", ASK)

    assert (answer["status"], answer["provider"]) == ("done", "fake")
    assert again["status"] == "repeated" and again["run_id"] == answer["run_id"]
    [done] = await attempts()
    assert done.status == "done" and "fake" in done.summary


async def test_runs_belong_to_their_person(clean) -> None:
    await ai.run("outings", ASK)
    with as_user(OTHER):
        assert await attempts() == []


@pytest.mark.parametrize(
    "host", ["localhost", "kernel", "127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"]
)
async def test_web_fetch_never_reaches_inside(host) -> None:
    with pytest.raises(Refused):
        await public_host(host)


async def test_web_fetch_checks_every_redirect() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    web = Web(httpx.AsyncClient(transport=httpx.MockTransport(reply)))
    with pytest.raises(Refused):
        await web.fetch("http://93.184.216.34/start")


async def test_web_fetch_reads_a_page_as_text() -> None:
    page = (
        "<html><head><style>p{}</style></head>"
        "<body><h1>Jazz</h1><p>Friday &amp; Saturday</p></body></html>"
    )

    def reply(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    web = Web(httpx.AsyncClient(transport=httpx.MockTransport(reply)))
    shown = await web.fetch("http://93.184.216.34/agenda")
    assert "Jazz" in shown and "Friday & Saturday" in shown and "p{}" not in shown
