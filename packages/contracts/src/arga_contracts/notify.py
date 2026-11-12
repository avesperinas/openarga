from __future__ import annotations

import os
import sys
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import date, datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from arga_contracts.records import Every, spaces
from arga_tenancy import as_user, kernel_url, user_headers

_zone: ContextVar[ZoneInfo | None] = ContextVar("arga_notify_zone", default=None)


def instance_zone() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("OPENARGA_TIMEZONE") or "UTC")
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def zone() -> ZoneInfo:
    return _zone.get() or instance_zone()


def __getattr__(name: str) -> ZoneInfo:
    if name == "MADRID":
        return zone()
    raise AttributeError(name)


def at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, zone())


async def zone_of_person(client: httpx.AsyncClient) -> ZoneInfo:
    try:
        response = await client.get(
            f"{kernel_url()}/me/preferences", headers=user_headers(), timeout=10.0
        )
        response.raise_for_status()
        return ZoneInfo(response.json()["timezone"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return instance_zone()


def notification(
    kind: str, key: str, title: str, href: str, when: datetime, body: str | None = None
) -> dict[str, Any]:
    return {
        "kind": kind,
        "key": key,
        "title": title[:120],
        "body": body[:400] if body else None,
        "href": href,
        "at": when.isoformat(),
    }


async def sync(client: httpx.AsyncClient, app: str, items: list[dict[str, Any]]) -> dict | None:
    try:
        response = await client.post(
            f"{kernel_url()}/internal/capabilities/notify.sync",
            json={"items": items},
            headers={**user_headers(), "x-arga-module": app},
            timeout=20.0,
        )
    except httpx.HTTPError:
        return None
    return response.json() if response.status_code == 200 else None


async def refresh(
    client: httpx.AsyncClient,
    engine: Callable[[], AsyncEngine],
    app: str,
    build: Callable[[AsyncConnection], Awaitable[list[dict[str, Any]]]],
    every: Every,
    user: UUID,
) -> dict | None:
    if not every.due(user):
        return None
    try:
        with as_user(user, await spaces(client)):
            token = _zone.set(await zone_of_person(client))
            try:
                async with engine().begin() as connection:
                    await connection.execute(text(f'set local role "mod_{app}"'))
                    items = await build(connection)
            finally:
                _zone.reset(token)
            return await sync(client, app, items)
    except Exception as error:  # noqa: BLE001 - los avisos no paran lo que publica la app
        print(f"avisos · {app}: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return None
