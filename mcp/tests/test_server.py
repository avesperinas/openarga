# ruff: noqa: F811

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import httpx
import httpx2
import pytest
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_stack import PERSON, TEST_DATABASE_URL, migrated, settings, stack  # noqa: F401, I001
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from arga_mcp.main import Settings, create_app

SOURCE = Path(__file__).resolve().parents[1] / "src" / "arga_mcp"


@contextlib.asynccontextmanager
async def served(stack: httpx.AsyncClient, settings: Settings):
    app = create_app(settings, stack)
    async with app.router.lifespan_context(app):
        yield app


@contextlib.asynccontextmanager
async def connected(
    app, scopes: str, mode: str = "legacy", user: str | None = None, spaces: str = ""
):
    headers = {
        "x-arga-subject": "owner",
        "x-arga-scopes": scopes,
        "x-arga-user": user or str(PERSON),
        **({"x-arga-spaces": spaces} if spaces else {}),
    }
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://mcp",
        headers=headers,
    )
    async with (
        http,
        Client(
            streamable_http_client("http://mcp/mcp", http_client=http), mode=mode, cache=None
        ) as client,
    ):
        yield client


def _names(listed: dict) -> set[str]:
    return {item["name"] for section in listed["sections"] for item in section["items"]} | {
        item["name"] for item in listed["cart"]
    }


def test_the_server_code_does_not_know_any_module_by_name() -> None:
    for path in SOURCE.glob("*.py"):
        source = path.read_text()
        assert "training" not in source and "shopping" not in source, (
            f"{path.name} nombra un módulo"
        )


async def test_it_lists_the_tools_the_token_can_use(settings, stack) -> None:
    async with served(stack, settings) as app, connected(app, "training:read") as client:
        listed = await client.list_tools()

    assert sorted(tool.name for tool in listed.tools) == [
        "training_find_exercises",
        "training_get_activities",
        "training_get_muscles",
        "training_get_progress",
        "training_get_sessions",
        "training_summarise_training",
    ]
    assert listed.tools[0].input_schema["type"] == "object"


async def test_write_scope_sees_the_write_tools_too(settings, stack) -> None:
    async with served(stack, settings) as app, connected(app, "shopping:write") as client:
        listed = await client.list_tools()

    assert "shopping_add_to_list" in {tool.name for tool in listed.tools}


@pytest.mark.parametrize("mode", ["legacy", "auto"])
async def test_a_read_tool_returns_real_data(settings, stack, mode: str) -> None:
    async with (
        served(stack, settings) as app,
        connected(app, "training:read", mode) as client,
    ):
        result = await client.call_tool("training_find_exercises", {"query": "press"})

    assert not result.is_error, result.content
    variants = json.loads(result.content[0].text)["variants"]
    assert variants, "el catálogo sembrado trae presses"
    assert all("press" in f"{v['exercise']} {v['variant']}".lower() for v in variants)


async def test_a_read_token_calling_a_write_tool_gets_403_from_postgres(settings, stack) -> None:
    async with served(stack, settings) as app, connected(app, "shopping:read") as client:
        result = await client.call_tool("shopping_add_to_list", {"items": [{"name": "Milk"}]})

    assert result.is_error
    assert result.content[0].text.startswith("403:")
    assert "mod_shopping_read" in result.content[0].text


async def test_a_write_token_can_write(settings, stack) -> None:
    async with served(stack, settings) as app, connected(app, "shopping:write") as client:
        written = await client.call_tool("shopping_add_to_list", {"items": [{"name": "Bread"}]})
        listed = json.loads(
            (await client.call_tool("shopping_get_shopping_list", {})).content[0].text
        )

    assert not written.is_error, written.content
    assert "Bread" in _names(listed)


async def test_what_a_tool_writes_belongs_to_the_person_the_gateway_resolved(
    settings, stack
) -> None:
    person = "6a0f3c2e-8d1b-4c7a-9e5f-2b4d6c8a0e13"
    async with (
        served(stack, settings) as app,
        connected(app, "shopping:write", user=person) as client,
    ):
        written = await client.call_tool("shopping_add_to_list", {"items": [{"name": "Lemons"}]})

    assert not written.is_error, written.content
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        owner = await connection.scalar(
            text(
                "select cast(i.user_id as text) from shopping.shopping_item i "
                "join shopping.shopping_product p on p.id = i.product_id where p.name = 'Lemons'"
            )
        )
    await engine.dispose()
    assert owner == person


async def test_two_people_call_the_same_tool_and_no_row_crosses(settings, stack) -> None:
    other = "4d3c2b1a-0f9e-4d8c-b7a6-5e4d3c2b1a09"
    async with served(stack, settings) as app:
        async with connected(app, "training:read shopping:write") as mine:
            await mine.call_tool("shopping_add_to_list", {"items": [{"name": "Oats"}]})
            seen_by_me = json.loads(
                (await mine.call_tool("training_find_exercises", {})).content[0].text
            )
        async with connected(app, "training:read shopping:write", user=other) as theirs:
            await theirs.call_tool("shopping_add_to_list", {"items": [{"name": "Basil"}]})
            their_list = json.loads(
                (await theirs.call_tool("shopping_get_shopping_list", {})).content[0].text
            )
            seen_by_them = json.loads(
                (await theirs.call_tool("training_find_exercises", {})).content[0].text
            )

    assert seen_by_me["variants"]
    assert seen_by_them["variants"] == []
    assert _names(their_list) == {"Basil"}


async def test_without_scopes_nothing_is_listed_and_nothing_runs(settings, stack) -> None:
    async with served(stack, settings) as app, connected(app, "") as client:
        listed = await client.list_tools()
        result = await client.call_tool("training_find_exercises", {})

    assert listed.tools == []
    assert result.is_error
    assert result.content[0].text.startswith("403:")


async def test_it_answers_its_probe_without_anything_behind(settings, stack) -> None:
    async with (
        served(stack, settings) as app,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as http,
    ):
        assert (await http.get("/healthz")).json() == {"status": "ok"}


async def test_the_spaces_travel_with_the_person_to_the_module(settings, stack) -> None:
    spaces = "0c0c0c0c-0000-4000-8000-00000000c0c0,0d0d0d0d-0000-4000-8000-00000000d0d0"
    sent = []

    async def record(request: httpx.Request) -> None:
        if "/tools/" in request.url.path:
            sent.append(request.headers.get("x-arga-spaces"))

    stack.event_hooks["request"].append(record)
    async with (
        served(stack, settings) as app,
        connected(app, "shopping:read", spaces=spaces) as client,
    ):
        result = await client.call_tool("shopping_get_shopping_list", {})

    assert not result.is_error, result.content
    assert sent == [spaces]
