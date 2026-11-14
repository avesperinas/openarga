from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from arga_module import preferences
from arga_tenancy import UserFromHeader
from money import api as ledger_api
from money.db import SCHEMA, engine
from money.tools import TOOLS, role_for_scopes

MODULE_ID = "money"
UI_ROOT = f"/{MODULE_ID}"
INSUFFICIENT_PRIVILEGE = "42501"

app = FastAPI(title="Money", version=os.environ.get("APP_VERSION", "dev"))
app.add_middleware(UserFromHeader)
app.include_router(ledger_api.router)


@app.middleware("http")
async def person_preferences(request: Request, call_next):
    token = preferences.use(preferences.from_headers(request.headers))
    try:
        return await call_next(request)
    finally:
        preferences.reset(token)


def ui_dist() -> Path:
    default = Path(__file__).resolve().parents[2] / "ui" / "dist"
    return Path(os.environ.get("UI_DIST", default))


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "module": MODULE_ID}


@app.get("/readyz")
async def readyz() -> dict:
    try:
        async with engine().connect() as connection:
            found = await connection.scalar(
                text("select 1 from information_schema.schemata where schema_name = :schema"),
                {"schema": SCHEMA},
            )
    except Exception as error:  # noqa: BLE001 -- any connection failure means "not ready"
        raise HTTPException(status_code=503, detail=f"no database: {error}") from error
    if not found:
        raise HTTPException(
            status_code=503,
            detail=f"schema '{SCHEMA}' does not exist yet; the kernel provisions it when it "
            f"registers the manifest",
        )
    if not (ui_dist() / "index.html").is_file():
        raise HTTPException(status_code=503, detail=f"the app is not built in {ui_dist()}")
    return {"status": "ready", "module": MODULE_ID, "schema": SCHEMA}


@app.get("/version")
async def version() -> dict:
    return {"service": MODULE_ID, "version": app.version}


@app.get("/tools")
async def list_tools() -> list[dict]:
    return [
        {"name": name, "input_schema": tool.arguments.model_json_schema()}
        for name, tool in TOOLS.items()
    ]


@app.post("/tools/{name}")
async def call_tool(name: str, request: Request, x_arga_scopes: str = Header(default="")) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"money has no tool '{name}'")
    role = role_for_scopes(set(x_arga_scopes.split()))
    if role is None:
        raise HTTPException(status_code=403, detail=f"no {MODULE_ID} scope in the call")
    try:
        arguments = tool.arguments.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        async with engine().begin() as connection:
            await connection.execute(text(f'set local role "{role}"'))
            return {"content": await tool.run(connection, arguments)}
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
            raise HTTPException(
                status_code=403, detail=f"Postgres does not let {role} do this: {name}"
            ) from error
        raise


@app.get(UI_ROOT + "/v1")
@app.get(UI_ROOT + "/v1/{path:path}")
async def moved(path: str = "") -> RedirectResponse:
    return RedirectResponse(f"{UI_ROOT}/{path}", status_code=308)


@app.get(UI_ROOT)
@app.get(UI_ROOT + "/{path:path}")
async def ui(path: str = "") -> FileResponse:
    root = ui_dist().resolve()
    candidate = (root / path).resolve()
    if path and candidate.is_file() and candidate.is_relative_to(root):
        immutable = candidate.parent.name == "assets"
        return FileResponse(
            candidate,
            headers={
                "cache-control": "public, max-age=31536000, immutable" if immutable else "no-cache"
            },
        )
    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="the app is not built")
    return FileResponse(index, headers={"cache-control": "no-cache"})
