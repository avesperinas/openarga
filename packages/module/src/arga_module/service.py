from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module import preferences
from arga_module.db import engine
from arga_module.publisher import Publisher
from arga_tenancy import USER_HEADER, UserFromHeader, current_user, require_person
from arga_widgets import Act

INSUFFICIENT_PRIVILEGE = "42501"
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

Renderer = Callable[[AsyncConnection], Awaitable[dict]]
Action = Callable[..., Awaitable[Any]]


def publishes_in_process() -> bool:
    return os.environ.get("PUBLISH_IN_PROCESS", "1") != "0"


class Service:
    def __init__(
        self,
        module_id: str,
        title: str,
        *,
        tools: Mapping[str, Any] | None = None,
        role_for_scopes: Callable[[set[str]], str | None] | None = None,
        widgets: Mapping[str, Renderer] | None = None,
        panel: Renderer | None = None,
        actions: Mapping[str, Action] | None = None,
        errors: Mapping[type[Exception], int] | None = None,
        publisher: Publisher | None = None,
        ui: bool = True,
        ui_dist: Path | None = None,
    ) -> None:
        self.module_id = module_id
        self.schema = module_id
        self.app_role = f"mod_{module_id}"
        self.reader_role = f"mod_{module_id}_read"
        self.ui_root = f"/{module_id}"
        self.tools = dict(tools or {})
        self.role_for_scopes = role_for_scopes
        self.widgets = dict(widgets or {})
        self.panel = panel
        self.actions = dict(actions or {})
        self.errors = dict(errors or {})
        self.publisher = publisher
        self.ui = ui
        if ui and ui_dist is None:
            raise ValueError(
                f"{module_id}: una app que se sirve necesita saber dónde está construida"
            )
        self._ui_dist = ui_dist

        self.app = FastAPI(
            title=title, version=os.environ.get("APP_VERSION", "dev"), lifespan=self._lifespan
        )
        self.app.add_middleware(UserFromHeader)
        self.app.middleware("http")(self._preferences_from_headers)
        if publisher is not None:
            self.app.middleware("http")(self._touch_after_writes)
        for error, status in self.errors.items():
            self.app.add_exception_handler(error, self._error_handler(status))
        self._routes()

    @contextlib.asynccontextmanager
    async def as_role(self, role: str) -> AsyncIterator[AsyncConnection]:
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            yield connection

    def as_app(self) -> contextlib.AbstractAsyncContextManager[AsyncConnection]:
        return self.as_role(self.app_role)

    def as_reader(self) -> contextlib.AbstractAsyncContextManager[AsyncConnection]:
        return self.as_role(self.reader_role)

    async def edit(self, action: Action, *args: Any) -> Any:
        async with self.as_app() as connection:
            return await action(connection, *args)

    def client(self) -> httpx.AsyncClient:
        client = getattr(self.app.state, "client", None)
        if client is None:
            raise HTTPException(status_code=503, detail="el cliente del kernel no está listo")
        return client

    def ui_dist(self) -> Path:
        return Path(os.environ.get("UI_DIST", str(self._ui_dist)))

    @contextlib.asynccontextmanager
    async def _lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        app.state.client = httpx.AsyncClient()
        running = None
        if self.publisher is not None and publishes_in_process():
            running = asyncio.create_task(self.publisher.loop(app.state.client))
        try:
            yield
        finally:
            if running is not None:
                running.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await running
            await app.state.client.aclose()

    async def _preferences_from_headers(self, request: Request, call_next):
        token = preferences.use(preferences.from_headers(request.headers))
        try:
            return await call_next(request)
        finally:
            preferences.reset(token)

    async def _touch_after_writes(self, request: Request, call_next):
        response = await call_next(request)
        reads = request.url.path.startswith("/tools/") and f"{self.module_id}:write" not in (
            request.headers.get("x-arga-scopes", "").split()
        )
        if request.method in WRITES and not reads and 200 <= response.status_code < 300:
            with contextlib.suppress(ValueError):
                who = request.headers.get(USER_HEADER)
                user = UUID(who) if who else current_user.get()
                if user is not None:
                    self.publisher.touch(user)
        return response

    def _error_handler(self, status: int):
        async def handle(request: Request, error: Exception) -> JSONResponse:
            del request
            detail = f"no existe: {error}" if status == 404 else str(error)
            return JSONResponse(status_code=status, content={"detail": detail})

        return handle

    def _routes(self) -> None:
        app = self.app
        module_id = self.module_id

        @app.get("/healthz")
        async def healthz() -> dict:
            return {"status": "ok", "module": module_id}

        @app.get("/readyz")
        async def readyz() -> dict:
            try:
                async with engine().connect() as connection:
                    found = await connection.scalar(
                        text(
                            "select 1 from information_schema.schemata where schema_name = :schema"
                        ),
                        {"schema": self.schema},
                    )
            except Exception as error:  # noqa: BLE001 -- cualquier fallo de conexión es "no listo"
                raise HTTPException(
                    status_code=503, detail=f"sin base de datos: {error}"
                ) from error
            if not found:
                raise HTTPException(
                    status_code=503,
                    detail=f"el schema '{self.schema}' no existe todavía; lo aprovisiona el kernel "
                    f"al registrar el manifiesto",
                )
            if self.ui and not (self.ui_dist() / "index.html").is_file():
                raise HTTPException(
                    status_code=503, detail=f"la app no está construida en {self.ui_dist()}"
                )
            return {"status": "ready", "module": module_id, "schema": self.schema}

        @app.get("/version")
        async def version() -> dict:
            return {"service": module_id, "version": app.version}

        @app.get("/me")
        async def me() -> dict[str, str]:
            return {"user_id": str(require_person())}

        @app.get("/widgets/{widget_id}")
        async def widget(widget_id: str) -> dict:
            renderer = self.widgets.get(widget_id)
            if renderer is None:
                raise HTTPException(
                    status_code=404, detail=f"{module_id} no tiene el widget '{widget_id}'"
                )
            async with self.as_reader() as connection:
                return await renderer(connection)

        @app.get("/panel")
        async def panel() -> dict:
            if self.panel is None:
                raise HTTPException(status_code=404, detail=f"{module_id} no tiene panel")
            async with self.as_reader() as connection:
                return await self.panel(connection)

        @app.post("/widgets/{widget_id}/act")
        async def widget_act(widget_id: str, request: Act) -> dict:
            action = self.actions.get(widget_id)
            if action is None:
                raise HTTPException(status_code=404, detail=f"en '{widget_id}' no se tacha nada")
            if request.verb == "add":
                item_id = request.id.strip()
                if not item_id:
                    raise HTTPException(status_code=422, detail="no hay nada que añadir")
            else:
                try:
                    item_id = str(UUID(request.id))
                except ValueError as error:
                    raise HTTPException(
                        status_code=422, detail="no es algo de la tarjeta"
                    ) from error
            await self.edit(action, request.verb, item_id)
            return await widget(widget_id)

        @app.get("/tools")
        async def list_tools() -> list[dict]:
            return [
                {"name": name, "input_schema": tool.arguments.model_json_schema()}
                for name, tool in self.tools.items()
            ]

        @app.post("/tools/{name}")
        async def call_tool(
            name: str, request: Request, x_arga_scopes: str = Header(default="")
        ) -> dict:
            tool = self.tools.get(name)
            if tool is None:
                raise HTTPException(
                    status_code=404, detail=f"{module_id} no tiene la tool '{name}'"
                )
            role = (
                self.role_for_scopes(set(x_arga_scopes.split())) if self.role_for_scopes else None
            )
            if role is None:
                raise HTTPException(
                    status_code=403, detail=f"ningún scope de {module_id} en la llamada"
                )
            try:
                arguments = tool.arguments.model_validate(await request.json())
            except (ValidationError, ValueError) as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            extra = {"client": self.client()} if getattr(tool, "asks_the_hub", False) else {}
            try:
                if getattr(tool, "own_transactions", False):
                    return {
                        "content": await tool.run(lambda: self.as_role(role), arguments, **extra)
                    }
                async with self.as_role(role) as connection:
                    return {"content": await tool.run(connection, arguments, **extra)}
            except DBAPIError as error:
                if getattr(error.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
                    raise HTTPException(
                        status_code=403, detail=f"Postgres no deja a {role} hacer esto: {name}"
                    ) from error
                raise

    def serve_ui(self) -> None:

        async def ui(path: str = "") -> FileResponse:
            root = self.ui_dist().resolve()
            candidate = (root / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(root):
                immutable = candidate.parent.name == "assets"
                return FileResponse(
                    candidate, headers={"cache-control": IMMUTABLE if immutable else REVALIDATE}
                )
            if path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
                raise HTTPException(status_code=404, detail=f"no existe: {path}")
            index = root / "index.html"
            if not index.is_file():
                raise HTTPException(status_code=503, detail="la app no está construida")
            return FileResponse(index, headers={"cache-control": REVALIDATE})

        self.app.get(self.ui_root)(ui)
        self.app.get(self.ui_root + "/{path:path}")(ui)
