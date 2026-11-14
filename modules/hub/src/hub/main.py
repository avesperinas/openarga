from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from arga_module.service import Service
from arga_tenancy import as_user, kernel_url, require_person
from hub import (
    ai,
    apps,
    banks,
    capabilities,
    catalogue,
    claude_run,
    connections,
    credentials,
    google_auth,
    plugs,
    push,
    rules,
    statements,
    sync,
)
from hub.capabilities import CAPABILITIES
from hub.db import as_module
from hub.providers import SourceError, imap
from hub.tools import TOOLS, role_for_scopes
from hub.widgets import RENDERERS
from hub.words import say

MODULE_ID = "hub"
UI_ROOT = f"/{MODULE_ID}"

service = Service(
    MODULE_ID,
    "Hub",
    tools=TOOLS,
    role_for_scopes=role_for_scopes,
    widgets=RENDERERS,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
app.include_router(ai.router)
_started = app.router.lifespan_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    credentials.masters()
    async with _started(app):
        yield


app.router.lifespan_context = lifespan

as_app = as_module


@app.get("/catalogue")
async def read_catalogue() -> list[dict]:
    found = await plugs.inlets(capabilities.kernel_transport())
    listed = catalogue.listed()
    for category in listed:
        for item in category["providers"]:
            known = catalogue.BY_ID.get(item["id"])
            item["inlets"] = (
                [
                    {
                        "key": inlet["key"],
                        "app": inlet["name"],
                        "title": inlet["title"],
                        "settings": inlet.get("settings") or [],
                    }
                    for inlet in plugs.accepting(known, found)
                ]
                if known
                else []
            )
    return listed


@app.get("/apps")
async def read_apps() -> dict:
    transport = capabilities.kernel_transport()
    found, others = apps.by_app(await apps.modules(transport), await plugs.inlets(transport))
    return {"apps": found, "others": others}


@app.get("/offers/{provider_id}/search")
async def search_offer(
    provider_id: str, ask: str, query: str | None = None, parent: str | None = None
) -> dict:
    require_person()
    try:
        return await capabilities.search(provider_id, ask, query, parent)
    except connections.Refused as error:
        raise refused(error) from error


@app.get("/connections")
async def list_connections() -> list[dict]:
    require_person()
    async with as_app() as connection:
        found = await connections.listed(connection)
    return [
        connections.summary(item)
        for item in sorted(found, key=lambda item: connections.URGENCY[item.state])
    ]


class ConnectionIn(BaseModel):
    provider: str
    label: str | None = None
    secrets: dict[str, str] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    bank: str | None = None
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "ES"
    plugs: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BanksIn(BaseModel):
    country: Annotated[str, Field(pattern=r"^[A-Z]{2}$")] = "ES"
    secrets: dict[str, str] = Field(default_factory=dict)


class CredentialIn(BaseModel):
    value: str = Field(max_length=credentials.MAX_LENGTH)


class LabelIn(BaseModel):
    label: str


def refused(error: connections.Refused) -> HTTPException:
    return HTTPException(status_code=error.status, detail=str(error))


async def detail_or_404(connection, connection_id: UUID) -> dict:
    found = await connections.detail(connection, connection_id)
    if found is None:
        raise HTTPException(status_code=404, detail="that connection does not exist")
    return found


async def tell(found: dict, removed: bool = False) -> dict:
    async with httpx.AsyncClient(
        base_url=kernel_url(), transport=capabilities.kernel_transport(), timeout=10.0
    ) as kernel:
        await sync.announce_connection(kernel, found, removed)
    return found


def source_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=capabilities.source_transport(), timeout=60.0)


@app.post("/connections", status_code=201)
async def create_connection(request: ConnectionIn) -> dict:
    require_person()
    try:
        provider = catalogue.provider(request.provider)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    try:
        if provider.oauth:
            async with as_app() as connection:
                created, url = await google_auth.start(connection, request.label, request.secrets)
                found = await detail_or_404(connection, created)
            return {**await tell(found), "authorization_url": url}
        if provider.authorizes:
            if not request.bank:
                raise connections.Refused(say("bank.choose"))
            async with source_client() as client, as_app() as connection:
                created, url = await banks.start(
                    connection,
                    client,
                    request.bank,
                    request.country,
                    request.label,
                    request.secrets,
                )
                found = await detail_or_404(connection, created)
            return {**await tell(found), "authorization_url": url}
        token = None
        found_inlets = await plugs.inlets(capabilities.kernel_transport())
        label = connections.clean_label(provider, request.label)
        async with as_app() as connection:
            created = await connections.create(
                connection,
                request.provider,
                request.label,
                request.secrets,
                config=request.settings or None,
                plugs=plugs.plugs_for(provider, found_inlets, request.plugs, label),
            )
            if "push" in provider.capabilities:
                token = await push.store(connection, provider.id, require_person(), created)
            found = await detail_or_404(connection, created)
    except connections.Refused as error:
        raise refused(error) from error
    told = await tell(found)
    return {**told, "ingest_token": token} if token else told


@app.post("/connections/{connection_id}/token")
async def new_token(connection_id: UUID) -> dict:
    person = require_person()
    async with as_app() as connection:
        row = (await connection.execute(ROW, {"id": connection_id})).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="that connection does not exist")
        provider = catalogue.provider(row.provider)
        if "push" not in provider.capabilities:
            raise HTTPException(
                status_code=409, detail=f"{provider.name} does not call with a token"
            )
        token = await push.store(connection, provider.id, person, connection_id)
        found = await detail_or_404(connection, connection_id)
    return {**found, "ingest_token": token}


@app.post("/push/{source}")
async def receive(source: str, request: Request, authorization: str | None = Header(None)) -> dict:
    receiver = push.RECEIVERS.get(source)
    if receiver is None:
        raise HTTPException(status_code=404, detail="no existe")
    provider_id, read = receiver
    unauthorised = HTTPException(
        status_code=401,
        detail="invalid ingest token",
        headers={"www-authenticate": "Bearer"},
    )
    try:
        user, connection_id, token = push.claimed(authorization)
    except push.Denied as error:
        raise unauthorised from error
    with as_user(user):
        try:
            async with as_app() as connection:
                row = await push.verify(connection, provider_id, connection_id, token)
        except push.Denied as error:
            raise unauthorised from error
        try:
            received = read(await request.json(), date.today())
        except (ValidationError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        async with as_app() as connection:
            run_id = await sync.start(connection, connection_id, "push", received.operation)
        result = sync.Outcome(run_id, "ok")
        async with httpx.AsyncClient(
            base_url=kernel_url(), transport=capabilities.kernel_transport(), timeout=60.0
        ) as kernel:
            try:
                await sync.publish_all(kernel, provider_id, received.events, result)
            except httpx.HTTPError as error:
                result.outcome = "error"
                result.detail = f"the kernel does not answer: {type(error).__name__}"
            result.detail = result.detail or (
                f"{len(received.events)} recibidos, {result.emitted} nuevos"
            )
            await sync.finish(kernel, row, provider_id, "push", received.operation, result)
    if result.outcome != "ok":
        raise HTTPException(status_code=503, detail=result.detail)
    return {"received": len(received.events), "new": result.emitted}


@app.get("/providers/enable_banking")
async def bank_app() -> dict:
    require_person()
    async with as_app() as connection:
        return {"app": await banks.has_app(connection), "redirect_url": banks.redirect_url()}


@app.post("/providers/enable_banking/banks")
async def list_banks(request: BanksIn) -> list[str]:
    require_person()
    try:
        async with source_client() as client, as_app() as connection:
            return await banks.banks(connection, client, request.country, request.secrets)
    except connections.Refused as error:
        raise refused(error) from error


@app.post("/connections/{connection_id}/reauthorize")
async def reauthorize(connection_id: UUID) -> dict:
    require_person()
    try:
        async with source_client() as client, as_app() as connection:
            row = (await connection.execute(ROW, {"id": connection_id})).one_or_none()
            if row is not None and catalogue.provider(row.provider).oauth:
                url = await google_auth.reauthorize(connection, connection_id)
            else:
                url = await banks.reauthorize(connection, client, connection_id)
    except connections.Refused as error:
        raise refused(error) from error
    return {"authorization_url": url}


ROW = text("""
    select id, provider, label, status, paused, config, consent_expires_at
    from hub.hub_connection where id = :id
""")


@app.post("/connections/{connection_id}/sync")
async def sync_now(connection_id: UUID) -> dict:
    require_person()
    async with as_app() as connection:
        row = (await connection.execute(ROW, {"id": connection_id})).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="that connection does not exist")
        provider = catalogue.provider(row.provider)
        if row.provider not in sync.CLIENTS or not provider.by_hand:
            raise HTTPException(status_code=409, detail=f"{provider.name} does not sync by hand")
        if row.paused or row.status != "active":
            raise HTTPException(status_code=409, detail=f"{row.label} is not active")
        left = sync.remaining(provider, await sync.used_today(connection, connection_id))
        if left == 0:
            raise HTTPException(
                status_code=409,
                detail=say("sync.no_access_left", label=row.label),
            )
    async with (
        source_client() as client,
        httpx.AsyncClient(
            base_url=kernel_url(), transport=capabilities.kernel_transport(), timeout=30.0
        ) as kernel,
    ):
        outcome = await sync.run(row, source=client, kernel=kernel)
    async with as_app() as connection:
        found = await detail_or_404(connection, connection_id)
    return {**found, "outcome": outcome.outcome, "outcome_detail": outcome.detail}


@app.get("/connections/{connection_id}")
async def read_connection(connection_id: UUID) -> dict:
    require_person()
    async with as_app() as connection:
        found = await detail_or_404(connection, connection_id)
    known = catalogue.BY_ID.get(found["provider"])
    reached = (
        plugs.accepting(known, await plugs.inlets(capabilities.kernel_transport())) if known else []
    )
    return {
        **found,
        "inlets": [
            {"key": one["key"], "app": one["name"], "title": one["title"], "settings": []}
            for one in reached
        ],
    }


@app.put("/connections/{connection_id}/credentials/{key}")
async def change_credential(connection_id: UUID, key: str, request: CredentialIn) -> dict:
    require_person()
    try:
        async with as_app() as connection:
            found = await detail_or_404(connection, connection_id)
            provider = catalogue.provider(found["provider"])
            if key not in {secret.key for secret in provider.secrets}:
                raise HTTPException(
                    status_code=404, detail=f"{provider.name} does not ask for '{key}'"
                )
            value = connections.clean_secret(provider, key, request.value)
            targets = (
                list(
                    (
                        await connection.execute(
                            text("select id from hub.hub_connection where provider = :provider"),
                            {"provider": provider.id},
                        )
                    ).scalars()
                )
                if key in provider.shared
                else [connection_id]
            )
            for target in targets:
                await credentials.store(connection, provider.id, target, key, value)
            found = await detail_or_404(connection, connection_id)
    except connections.Refused as error:
        raise refused(error) from error
    return await tell(found)


@app.put("/connections/{connection_id}/label")
async def rename_connection(connection_id: UUID, request: LabelIn) -> dict:
    require_person()
    try:
        async with as_app() as connection:
            if not await connections.rename(connection, connection_id, request.label):
                raise HTTPException(status_code=404, detail="that connection does not exist")
            found = await detail_or_404(connection, connection_id)
    except connections.Refused as error:
        raise refused(error) from error
    return await tell(found)


class RelayIn(BaseModel):
    relay: bool


@app.put("/connections/{connection_id}/relay")
async def change_relay(connection_id: UUID, request: RelayIn) -> dict:
    require_person()
    async with as_app() as connection:
        if not await connections.set_relay(connection, connection_id, request.relay):
            raise HTTPException(status_code=404, detail="that Claude account does not exist")
        found = await detail_or_404(connection, connection_id)
    return await tell(found)


class RulesIn(BaseModel):
    rules: Annotated[list[dict[str, Any]], Field(max_length=rules.MAX_RULES)]


@app.put("/connections/{connection_id}/rules")
async def change_rules(connection_id: UUID, request: RulesIn) -> dict:
    require_person()
    try:
        async with as_app() as connection:
            if not await connections.set_rules(connection, connection_id, request.rules):
                raise HTTPException(status_code=404, detail="that mailbox does not exist")
            found = await detail_or_404(connection, connection_id)
    except connections.Refused as error:
        raise refused(error) from error
    return await tell(found)


@app.post("/connections/{connection_id}/rules/try")
async def try_rule(connection_id: UUID, request: dict[str, Any]) -> dict:
    require_person()
    try:
        rule = rules.clean(request)
    except rules.Invalid as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    async with as_app() as connection:
        found = await detail_or_404(connection, connection_id)
        if found["provider"] != "imap":
            raise HTTPException(status_code=404, detail="that mailbox does not exist")
        config = await connections.config_of(connection, connection_id)
        secrets = await sync.secrets_of(connection, catalogue.provider("imap"), connection_id)
    if not secrets.get(imap.PASSWORD):
        raise HTTPException(status_code=422, detail=say("mailbox.missing_password"))
    try:
        results = await asyncio.to_thread(imap.trial, config, secrets[imap.PASSWORD], rule)
    except SourceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"results": results}


async def pause(connection_id: UUID, paused: bool) -> dict:
    require_person()
    async with as_app() as connection:
        if not await connections.set_paused(connection, connection_id, paused):
            raise HTTPException(status_code=404, detail="that connection does not exist")
        found = await detail_or_404(connection, connection_id)
    return await tell(found)


@app.post("/connections/{connection_id}/pause")
async def pause_connection(connection_id: UUID) -> dict:
    return await pause(connection_id, True)


@app.post("/connections/{connection_id}/resume")
async def resume_connection(connection_id: UUID) -> dict:
    return await pause(connection_id, False)


@app.delete("/connections/{connection_id}", status_code=204)
async def remove_connection(connection_id: UUID) -> Response:
    require_person()
    async with as_app() as connection:
        found = await detail_or_404(connection, connection_id)
        await connections.remove(connection, connection_id)
    await tell(found, removed=True)
    return Response(status_code=204)


@app.get("/claude-run")
async def read_claude_run() -> dict:
    require_person()
    modules = await apps.modules(capabilities.kernel_transport())
    async with as_app() as connection:
        granted = {grant.app: grant for grant in await claude_run.grants(connection)}
    return {
        "configured": bool(claude_run.client_secret()),
        "apps": [
            {
                "id": one.id,
                "name": one.name,
                "granted": granted[one.id].model_dump(mode="json") if one.id in granted else None,
            }
            for one in claude_run.runners(modules)
        ],
    }


@app.get("/claude-run/authorize")
async def authorize_claude_run(connection: UUID, app: str) -> RedirectResponse:
    require_person()
    modules = await apps.modules(capabilities.kernel_transport())
    try:
        async with as_app() as database:
            url = await claude_run.authorize(database, connection, app, modules)
    except claude_run.Refused as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    return RedirectResponse(url, status_code=303)


@app.get("/claude-run/callback")
async def claude_run_callback(state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    require_person()
    if error or not (state and code):
        return RedirectResponse(f"{UI_ROOT}/?claude=cancelado", status_code=303)
    try:
        async with httpx.AsyncClient(timeout=30.0) as auth, as_app() as database:
            app_id, account = await claude_run.finish_grant(database, auth, code, state)
    except (claude_run.Refused, httpx.HTTPError):
        return RedirectResponse(f"{UI_ROOT}/?claude=fallo", status_code=303)
    return RedirectResponse(f"{UI_ROOT}/{account}?claude={app_id}", status_code=303)


@app.delete("/claude-run/{app_id}", status_code=204)
async def revoke_claude_run(app_id: str) -> Response:
    require_person()
    async with httpx.AsyncClient(timeout=30.0) as auth, as_app() as database:
        removed = await claude_run.revoke(database, auth, app_id)
    if not removed:
        raise HTTPException(status_code=404, detail="that app had no permission")
    return Response(status_code=204)


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict[str, Any]:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="hub has no MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="only the kernel asks hub for capabilities")
    handler = CAPABILITIES.get(capability)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"hub cannot do '{capability}'")
    require_person()
    try:
        body = await request.json()
    except ValueError as error:
        raise HTTPException(status_code=422, detail="el cuerpo no es JSON") from error
    try:
        return await handler(x_arga_module, body)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except connections.Refused as error:
        raise refused(error) from error
    except IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="that id already belongs to another connection"
        ) from error


class StatementFile(BaseModel):
    name: Annotated[str, Field(max_length=200)]
    content: Annotated[str, Field(max_length=5_000_000)]


class StatementsIn(BaseModel):
    files: Annotated[list[StatementFile], Field(min_length=1, max_length=12)]


@app.post("/statements")
async def upload_statements(body: StatementsIn) -> dict[str, Any]:
    require_person()
    today = date.today()
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        base_url=kernel_url(), transport=capabilities.kernel_transport(), timeout=30.0
    ) as kernel:
        for file in body.files:
            try:
                found = statements.read(file.content, today)
            except statements.StatementError as error:
                results.append({"file": file.name, "problem": str(error)})
                continue
            outcome = sync.Outcome(UUID(int=0), "ok")
            try:
                await sync.publish_all(
                    kernel, statements.SOURCE, statements.events_of(found), outcome
                )
            except httpx.HTTPError as error:
                raise HTTPException(
                    status_code=502, detail="the kernel did not take the statement"
                ) from error
            results.append(
                {
                    "file": file.name,
                    "entity": found.entity,
                    "accounts": [account.name for account in found.accounts],
                    "balances": len(found.balances),
                    "movements": len(found.movements),
                    "new": outcome.emitted,
                    "repeated": outcome.duplicated,
                    "skipped": found.skipped,
                }
            )
    return {"files": results}


@app.get(UI_ROOT + "/callback")
async def callback(state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    require_person()
    if error or not (state and code):
        return RedirectResponse(f"{UI_ROOT}/?banco=cancelado", status_code=303)
    try:
        async with source_client() as client, as_app() as connection:
            connection_id, config = await banks.finish(connection, client, state, code)
            found = await detail_or_404(connection, connection_id)
    except banks.UnknownAuthorisation:
        return RedirectResponse(f"{UI_ROOT}/?banco=desconocido", status_code=303)
    except connections.Refused:
        return RedirectResponse(f"{UI_ROOT}/?banco=fallo", status_code=303)
    async with httpx.AsyncClient(
        base_url=kernel_url(), transport=capabilities.kernel_transport(), timeout=30.0
    ) as kernel:
        await sync.publish_events(
            kernel, banks.PROVIDER, banks.account_events(connection_id, config)
        )
        await sync.announce_connection(kernel, found)
    said = "conectado" if config.get("accounts") else "sin-cuentas"
    return RedirectResponse(f"{UI_ROOT}/{connection_id}?banco={said}", status_code=303)


@app.get(UI_ROOT + "/google/callback")
async def google_callback(state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    require_person()
    if error or not (state and code):
        return RedirectResponse(f"{UI_ROOT}/?google=cancelado", status_code=303)
    try:
        async with source_client() as client, as_app() as connection:
            connection_id = await google_auth.finish(connection, client, state, code)
            found = await detail_or_404(connection, connection_id)
    except google_auth.UnknownAuthorisation:
        return RedirectResponse(f"{UI_ROOT}/?google=desconocido", status_code=303)
    except connections.Refused:
        return RedirectResponse(f"{UI_ROOT}/?google=fallo", status_code=303)
    await tell(found)
    return RedirectResponse(f"{UI_ROOT}/{connection_id}?google=conectado", status_code=303)


service.serve_ui()
