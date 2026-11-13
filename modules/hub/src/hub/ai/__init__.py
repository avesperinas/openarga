from __future__ import annotations

import hashlib
from typing import Annotated, Any

import httpx
import httpx2
import jsonschema
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from arga_contracts.ai import ExtractRequest, ExtractResponse, RunRequest, RunResponse
from arga_contracts.ai import Usage as UsageOut
from arga_crypto import NotConfigured
from arga_tenancy import require_person
from hub.ai import ledger, settings
from hub.ai.providers import ProviderError, Usage
from hub.connections import Refused
from hub.db import as_module

router = APIRouter(tags=["ai"])


def source_transport() -> httpx.AsyncBaseTransport | None:
    return None


def anthropic_transport() -> httpx2.AsyncBaseTransport | None:
    return None


def _anthropic_client() -> httpx2.AsyncClient | None:
    transport = anthropic_transport()
    return None if transport is None else httpx2.AsyncClient(transport=transport)


async def extract(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = ExtractRequest.model_validate(body)
    try:
        jsonschema.Draft202012Validator.check_schema(request.output_schema)
    except jsonschema.SchemaError as error:
        raise Refused(f"output_schema is not a JSON Schema: {error.message}") from error

    async with as_module() as connection:
        found = await settings.effective(connection)
        try:
            model = found.model(request.role)
        except settings.Unavailable as error:
            raise Refused(str(error), 503) from error
        remaining = await ledger.left(connection, found.monthly_tokens)
        status = "over_budget" if remaining == 0 else "running"
        attempt = await ledger.open_attempt(
            connection,
            app=module,
            capability="extract",
            role=request.role,
            provider=found.provider,
            model=model,
            status=status,
        )
    if status == "over_budget":
        raise Refused("this month's AI budget is spent", 429)

    usage = Usage()
    try:
        async with httpx.AsyncClient(transport=source_transport()) as client:
            provider = settings.provider_for(found, client, _anthropic_client())
            answer = await provider.extract(
                model, request.role, request.instructions, request.input, request.output_schema
            )
        usage = answer.usage
        jsonschema.validate(answer.output, request.output_schema)
    except (settings.Unavailable, NotConfigured) as error:
        await _close(attempt, "failed", usage, str(error))
        raise Refused(str(error), 503) from error
    except ProviderError as error:
        await _close(attempt, "failed", usage, str(error))
        raise Refused(str(error), 503 if error.retryable else 502) from error
    except jsonschema.ValidationError as error:
        detail = f"the answer does not match output_schema: {error.message}"
        await _close(attempt, "failed", usage, detail)
        raise Refused(detail, 502) from error

    await _close(attempt, "done", usage)
    output = answer.output if isinstance(answer.output, dict) else {"value": answer.output}
    return ExtractResponse(
        output=output,
        provider=provider.name,
        model=model,
        usage=UsageOut(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens),
    ).model_dump()


async def _close(attempt, status: str, usage: Usage, detail: str | None = None) -> None:
    async with as_module() as connection:
        await ledger.close_attempt(connection, attempt, status, usage, detail=detail)


async def run(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = RunRequest.model_validate(body)
    run_id = hashlib.sha256(f"{module}:{request.key}".encode()).hexdigest()[:16]
    return RunResponse(
        status="done",
        run_id=run_id,
        summary="The fake AI provider did nothing. Configure a provider in Connections.",
        provider="fake",
        model="fake",
    ).model_dump()


class KeyIn(BaseModel):
    key: Annotated[str, Field(min_length=8, max_length=500, pattern=r"^\S+$")]


@router.get("/ai/settings")
async def read_settings() -> settings.SettingsOut:
    require_person()
    async with as_module() as connection:
        return await settings.describe(connection)


@router.put("/ai/settings")
async def write_settings(body: settings.SettingsIn) -> settings.SettingsOut:
    require_person()
    async with as_module() as connection:
        await settings.save(connection, body)
        return await settings.describe(connection)


@router.put("/ai/key", status_code=204)
async def write_key(body: KeyIn) -> Response:
    require_person()
    try:
        async with as_module() as connection:
            await settings.save_key(connection, body.key)
    except NotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(status_code=204)


@router.delete("/ai/key", status_code=204)
async def forget_key() -> Response:
    require_person()
    async with as_module() as connection:
        await settings.save_key(connection, None)
    return Response(status_code=204)


class Spending(BaseModel):
    spent: int
    monthly_tokens: int | None
    attempts: list[ledger.Attempt]


@router.get("/ai/attempts")
async def attempts() -> Spending:
    require_person()
    async with as_module() as connection:
        found = await settings.effective(connection)
        return Spending(
            spent=await ledger.spent(connection),
            monthly_tokens=found.monthly_tokens,
            attempts=await ledger.recent(connection),
        )
