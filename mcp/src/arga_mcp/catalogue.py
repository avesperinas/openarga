from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

MODULE_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
TTL_SECONDS = 30
SUBJECT_HEADER = "x-arga-subject"
SCOPES_HEADER = "x-arga-scopes"
USER_HEADER = "x-arga-user"
SPACES_HEADER = "x-arga-spaces"


@dataclass(frozen=True)
class Tool:
    module: str
    name: str
    scope: str
    description: str
    input_schema: dict[str, Any]

    @property
    def exposed_name(self) -> str:
        return f"{self.module}_{self.name}"


@dataclass(frozen=True)
class Outcome:
    ok: bool
    content: Any
    status: int


def visible(tool: Tool, scopes: set[str]) -> bool:
    return tool.scope in scopes or (
        tool.scope == f"{tool.module}:read" and f"{tool.module}:write" in scopes
    )


class Catalogue:
    def __init__(self, client: httpx.AsyncClient, kernel_url: str, module_url_template: str):
        self.client = client
        self.kernel_url = kernel_url.rstrip("/")
        self.module_url_template = module_url_template
        self._cached: tuple[float, list[Tool]] | None = None

    def module_url(self, module: str) -> str:
        if not MODULE_ID.match(module):
            raise ValueError(f"id de módulo inválido en el catálogo: {module!r}")
        return self.module_url_template.format(module=module).rstrip("/")

    async def _schemas(self, module: str) -> dict[str, dict[str, Any]]:
        try:
            response = await self.client.get(f"{self.module_url(module)}/tools", timeout=5.0)
            response.raise_for_status()
            return {entry["name"]: entry["input_schema"] for entry in response.json()}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return {}

    async def tools(self) -> list[Tool]:
        if self._cached and time.monotonic() - self._cached[0] < TTL_SECONDS:
            return self._cached[1]

        response = await self.client.get(f"{self.kernel_url}/tools", timeout=5.0)
        response.raise_for_status()
        declared = response.json()

        modules = list(dict.fromkeys(entry["module"] for entry in declared))
        schemas = dict(
            zip(modules, await asyncio.gather(*(self._schemas(m) for m in modules)), strict=True)
        )
        tools: list[Tool] = []
        for entry in declared:
            schema = schemas[entry["module"]].get(entry["name"])
            if schema is None:
                continue
            tools.append(
                Tool(entry["module"], entry["name"], entry["scope"], entry["description"], schema)
            )

        self._cached = (time.monotonic(), tools)
        return tools

    async def for_scopes(self, scopes: set[str]) -> list[Tool]:
        return [tool for tool in await self.tools() if visible(tool, scopes)]

    async def call(
        self,
        exposed_name: str,
        arguments: dict[str, Any],
        subject: str,
        scopes: set[str],
        user: str = "",
        spaces: str = "",
    ) -> Outcome:
        tool = next((t for t in await self.tools() if t.exposed_name == exposed_name), None)
        if tool is None:
            return Outcome(False, f"no existe la tool '{exposed_name}'", 404)

        response = await self.client.post(
            f"{self.module_url(tool.module)}/tools/{tool.name}",
            json=arguments,
            headers={
                SUBJECT_HEADER: subject,
                SCOPES_HEADER: " ".join(sorted(scopes)),
                **({USER_HEADER: user} if user else {}),
                **({SPACES_HEADER: spaces} if user and spaces else {}),
            },
            timeout=30.0,
        )
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"detail": response.text}

        if response.is_success:
            return Outcome(True, body.get("content"), response.status_code)
        return Outcome(False, body.get("detail", body), response.status_code)
