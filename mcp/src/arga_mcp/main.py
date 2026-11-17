from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import httpx
import mcp_types as types
from mcp.server import Server
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from arga_mcp.catalogue import (
    SCOPES_HEADER,
    SPACES_HEADER,
    SUBJECT_HEADER,
    USER_HEADER,
    Catalogue,
)

SERVICE = "mcp"
INSTRUCTIONS = (
    "One person's data, split into modules. Each tool carries its module's prefix. Read tools "
    "look things up; write tools change something on the person's behalf, so use them only "
    "when asked."
)

trace = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class Settings:
    kernel_url: str = "http://kernel:8000"
    module_url_template: str = "http://{module}:8000"
    version: str = "dev"
    read_only: bool = False

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            kernel_url=os.environ.get("KERNEL_URL", cls.kernel_url),
            module_url_template=os.environ.get("MODULE_URL_TEMPLATE", cls.module_url_template),
            version=os.environ.get("APP_VERSION", cls.version),
            read_only=os.environ.get("OPENARGA_DEMO", "").lower() in ("1", "true", "yes"),
        )


def caller(ctx, read_only: bool = False) -> tuple[str, set[str]]:
    headers = _headers(ctx)
    scopes = set(headers.get(SCOPES_HEADER, "").split())
    if read_only:
        scopes = {f"{scope.rpartition(':')[0]}:read" for scope in scopes if ":" in scope}
    return headers.get(SUBJECT_HEADER, ""), scopes


def _headers(ctx):
    request = getattr(ctx, "request", None)
    return request.headers if request is not None else {}


def user_of(ctx) -> str:
    return _headers(ctx).get(USER_HEADER, "")


def spaces_of(ctx) -> str:
    return _headers(ctx).get(SPACES_HEADER, "")


def build_server(catalogue: Catalogue, version: str, read_only: bool = False) -> Server:
    async def list_tools(ctx, params) -> types.ListToolsResult:
        _, scopes = caller(ctx, read_only)
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=tool.exposed_name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
                for tool in await catalogue.for_scopes(scopes)
            ]
        )

    async def call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        subject, scopes = caller(ctx, read_only)
        outcome = await catalogue.call(
            params.name,
            dict(params.arguments or {}),
            subject,
            scopes,
            user_of(ctx),
            spaces_of(ctx),
        )
        trace.info(
            "tool %s · subject %s · scopes %s · %s",
            params.name,
            subject or "-",
            " ".join(sorted(scopes)) or "-",
            outcome.status,
        )
        if outcome.ok:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(outcome.content))],
                structured_content=outcome.content if isinstance(outcome.content, dict) else None,
            )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"{outcome.status}: {outcome.content}")],
            is_error=True,
        )

    return Server(
        "arga",
        version=version,
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def create_app(settings: Settings, client: httpx.AsyncClient | None = None) -> Starlette:
    client = client or httpx.AsyncClient()
    catalogue = Catalogue(client, settings.kernel_url, settings.module_url_template)
    server = build_server(catalogue, settings.version, settings.read_only)

    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def version(request: Request) -> JSONResponse:
        return JSONResponse({"service": SERVICE, "version": settings.version})

    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        custom_starlette_routes=[Route("/healthz", healthz), Route("/version", version)],
    )


def from_environment() -> Starlette:
    return create_app(Settings.from_environment())
