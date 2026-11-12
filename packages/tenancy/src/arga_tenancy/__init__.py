from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from contextvars import ContextVar
from uuid import UUID

import httpx
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

USER_HEADER = "x-arga-user"
SPACES_HEADER = "x-arga-spaces"
GUC = "arga.user_id"
SPACES_GUC = "arga.space_ids"

CURRENT_USER_SQL = f"nullif(current_setting('{GUC}', true), '')::uuid"
CURRENT_SPACES_SQL = f"coalesce(nullif(current_setting('{SPACES_GUC}', true), '')::uuid[], '{{}}')"

current_user: ContextVar[UUID | None] = ContextVar("arga_user", default=None)
current_spaces: ContextVar[tuple[UUID, ...]] = ContextVar("arga_spaces", default=())

TIMING_HEADER = "server-timing"
_db_time: ContextVar[list[float] | None] = ContextVar("arga_db_time", default=None)
_QUERY_STARTED = "arga_query_started"


def server_timing(db_seconds: float, queries: int, app_seconds: float) -> str:
    return (
        f'db;dur={db_seconds * 1000:.1f};desc="{queries} consultas", '
        f"app;dur={app_seconds * 1000:.1f}"
    )


@contextlib.contextmanager
def as_user(user_id: UUID | None, spaces: tuple[UUID, ...] = ()) -> Iterator[None]:
    token = current_user.set(user_id)
    spaces_token = current_spaces.set(tuple(spaces))
    try:
        yield
    finally:
        current_spaces.reset(spaces_token)
        current_user.reset(token)


def parse_spaces(raw: str) -> tuple[UUID, ...]:
    return tuple(UUID(part.strip()) for part in raw.split(",") if part.strip())


def format_spaces(spaces: tuple[UUID, ...]) -> str:
    return ",".join(str(space) for space in spaces)


def install(engine: AsyncEngine) -> AsyncEngine:

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _query_started(connection, cursor, statement, parameters, context, executemany) -> None:
        connection.info[_QUERY_STARTED] = time.perf_counter()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _query_done(connection, cursor, statement, parameters, context, executemany) -> None:
        started = connection.info.pop(_QUERY_STARTED, None)
        spent = _db_time.get()
        if started is not None and spent is not None:
            spent[0] += time.perf_counter() - started
            spent[1] += 1

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(connection) -> None:
        settings = []
        user = current_user.get()
        if user is not None:
            settings.append((GUC, str(user)))
        spaces = current_spaces.get()
        if spaces:
            settings.append((SPACES_GUC, "{" + format_spaces(spaces) + "}"))
        if settings:
            calls = ", ".join(
                f"set_config('{name}', ${n}, true)" for n, (name, _) in enumerate(settings, 1)
            )
            connection.exec_driver_sql(f"select {calls}", tuple(value for _, value in settings))

    return engine


ENGINE_OPTIONS = {"pool_size": 2, "max_overflow": 10, "pool_recycle": 1800, "pool_pre_ping": True}


def engine_for(url: str, **options) -> AsyncEngine:
    return install(create_async_engine(url, **{**ENGINE_OPTIONS, **options}))


class UserFromHeader:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        spent = [0.0, 0]
        timing = _db_time.set(spent)
        started = time.perf_counter()

        async def timed(message) -> None:
            if message["type"] == "http.response.start":
                value = server_timing(spent[0], int(spent[1]), time.perf_counter() - started)
                message = {
                    **message,
                    "headers": [
                        *message.get("headers", []),
                        (TIMING_HEADER.encode(), value.encode()),
                    ],
                }
            await send(message)

        try:
            await self._serve(scope, receive, timed)
        finally:
            _db_time.reset(timing)

    async def _serve(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = dict(scope["headers"])
        raw = headers.get(USER_HEADER.encode())
        if not raw:
            await self.app(scope, receive, send)
            return
        try:
            user = UUID(raw.decode("latin-1"))
            spaces = parse_spaces(headers.get(SPACES_HEADER.encode(), b"").decode("latin-1"))
        except ValueError:
            response = JSONResponse(
                status_code=400,
                content={"detail": f"{USER_HEADER} or {SPACES_HEADER} is not a list of ids"},
            )
            await response(scope, receive, send)
            return
        token = current_user.set(user)
        spaces_token = current_spaces.set(spaces)
        try:
            await self.app(scope, receive, send)
        finally:
            current_spaces.reset(spaces_token)
            current_user.reset(token)


def require_person() -> UUID:
    user = current_user.get()
    if user is None:
        raise HTTPException(
            status_code=422,
            detail=f"falta {USER_HEADER}: todo lo que se escribe es de alguien (ADR-0028)",
        )
    return user


def user_headers() -> dict[str, str]:
    user = current_user.get()
    if user is None:
        return {}
    spaces = current_spaces.get()
    return {USER_HEADER: str(user), **({SPACES_HEADER: format_spaces(spaces)} if spaces else {})}


def kernel_url() -> str:
    return os.environ.get("KERNEL_URL", "http://kernel:8000").rstrip("/")


async def users(client: httpx.AsyncClient) -> list[UUID]:
    response = await client.get(f"{kernel_url()}/internal/users", timeout=10.0)
    response.raise_for_status()
    return [UUID(row["id"]) for row in response.json()]


async def people(client: httpx.AsyncClient) -> list[tuple[UUID, tuple[UUID, ...]]]:
    response = await client.get(f"{kernel_url()}/internal/users", timeout=10.0)
    response.raise_for_status()
    return [
        (UUID(row["id"]), tuple(UUID(space) for space in row.get("spaces", [])))
        for row in response.json()
    ]


def from_environment() -> UUID | None:
    raw = os.environ.get("ARGA_USER_ID", "").strip()
    return UUID(raw) if raw else None
