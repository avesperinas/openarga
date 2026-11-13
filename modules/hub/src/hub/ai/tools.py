from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from arga_mcp.catalogue import Catalogue
from hub.ai.providers import ToolCall, ToolResult, ToolSpec

RESULT_LIMIT = 20_000
FETCH_BYTES = 2_000_000
REDIRECTS = 5
SEARCH_RESULTS = 8

WEB_SEARCH = ToolSpec(
    "web_search",
    "Search the web. Returns titles, addresses and snippets. Use web_fetch to read a result.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for."}},
        "required": ["query"],
    },
)
WEB_FETCH = ToolSpec(
    "web_fetch",
    "Read a public web page as plain text.",
    {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "An http or https address."}},
        "required": ["url"],
    },
)


def module_url_template() -> str:
    return os.environ.get("MODULE_URL_TEMPLATE", "http://{module}:8000")


def scopes_for(app: str, modules: set[str]) -> set[str]:
    return {f"{module}:read" for module in modules} | {f"{app}:write"}


def clipped(value: Any) -> str:
    shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return shown if len(shown) <= RESULT_LIMIT else shown[:RESULT_LIMIT] + "\n[cut]"


class Refused(Exception):
    pass


async def public_host(host: str) -> None:
    if not host or "." not in host.strip("."):
        raise Refused("only public hosts can be fetched")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [literal]
    else:
        try:
            found = await asyncio.get_running_loop().getaddrinfo(host, None)
        except socket.gaierror as error:
            raise Refused(f"{host} does not resolve") from error
        addresses = [ipaddress.ip_address(item[4][0]) for item in found]
    if not addresses or not all(address.is_global for address in addresses):
        raise Refused("only public hosts can be fetched")


TAGS = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.S | re.I)
MARKUP = re.compile(r"<[^>]+>")
SPACE = re.compile(r"[ \t\r\f\v]+")
LINES = re.compile(r"\n\s*\n+")


def text_of(body: str, kind: str) -> str:
    if "html" not in kind:
        return body
    stripped = MARKUP.sub("\n", TAGS.sub(" ", body))
    return LINES.sub("\n\n", SPACE.sub(" ", html.unescape(stripped))).strip()


@dataclass
class Web:
    client: httpx.AsyncClient

    @property
    def searcher(self) -> str | None:
        if os.environ.get("OPENARGA_SEARXNG_URL", "").strip():
            return "searxng"
        if os.environ.get("OPENARGA_BRAVE_KEY", "").strip():
            return "brave"
        return None

    def specs(self) -> list[ToolSpec]:
        return [WEB_SEARCH, WEB_FETCH] if self.searcher else [WEB_FETCH]

    async def search(self, query: str) -> list[dict[str, str]]:
        if self.searcher == "searxng":
            base = os.environ["OPENARGA_SEARXNG_URL"].rstrip("/")
            response = await self.client.get(
                f"{base}/search", params={"q": query, "format": "json"}, timeout=20.0
            )
            response.raise_for_status()
            items = response.json().get("results") or []
            found = [
                {
                    "title": i.get("title", ""),
                    "url": i.get("url", ""),
                    "snippet": i.get("content", ""),
                }
                for i in items
            ]
        elif self.searcher == "brave":
            response = await self.client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": SEARCH_RESULTS},
                headers={"x-subscription-token": os.environ["OPENARGA_BRAVE_KEY"]},
                timeout=20.0,
            )
            response.raise_for_status()
            items = (response.json().get("web") or {}).get("results") or []
            found = [
                {
                    "title": i.get("title", ""),
                    "url": i.get("url", ""),
                    "snippet": i.get("description", ""),
                }
                for i in items
            ]
        else:
            raise Refused("web search is not configured")
        return found[:SEARCH_RESULTS]

    async def fetch(self, url: str) -> str:
        for _ in range(REDIRECTS + 1):
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https"):
                raise Refused("only http and https addresses can be fetched")
            await public_host(parts.hostname or "")
            async with self.client.stream(
                "GET", url, timeout=20.0, follow_redirects=False
            ) as response:
                if response.is_redirect and "location" in response.headers:
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code >= 400:
                    raise Refused(f"{url} answered {response.status_code}")
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > FETCH_BYTES:
                        break
                kind = response.headers.get("content-type", "")
                return text_of(body[:FETCH_BYTES].decode("utf-8", "replace"), kind)
        raise Refused("too many redirects")


class Toolbox:
    def __init__(
        self,
        app: str,
        user: str,
        spaces: str,
        modules: httpx.AsyncClient,
        web: Web | None,
        kernel_url: str,
    ) -> None:
        self.app = app
        self.user = user
        self.spaces = spaces
        self.web = web
        self.catalogue = Catalogue(modules, kernel_url, module_url_template())
        self.scopes: set[str] = set()

    async def specs(self) -> list[ToolSpec]:
        tools = await self.catalogue.tools()
        self.scopes = scopes_for(self.app, {tool.module for tool in tools})
        visible = await self.catalogue.for_scopes(self.scopes)
        found = [
            ToolSpec(tool.exposed_name, tool.description, tool.input_schema) for tool in visible
        ]
        return found + (self.web.specs() if self.web else [])

    async def call(self, call: ToolCall) -> ToolResult:
        try:
            if self.web and call.name == WEB_SEARCH.name:
                return ToolResult(
                    call, clipped(await self.web.search(str(call.arguments.get("query", ""))))
                )
            if self.web and call.name == WEB_FETCH.name:
                return ToolResult(
                    call, clipped(await self.web.fetch(str(call.arguments.get("url", ""))))
                )
            outcome = await self.catalogue.call(
                call.name,
                call.arguments,
                subject=f"ai:{self.app}",
                scopes=self.scopes,
                user=self.user,
                spaces=self.spaces,
            )
        except (Refused, httpx.HTTPError, ValueError) as error:
            return ToolResult(call, str(error) or type(error).__name__, error=True)
        return ToolResult(call, clipped(outcome.content), error=not outcome.ok)
