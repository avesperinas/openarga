from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text

from arga_tenancy import require_person, user_headers
from kernel import notifications
from kernel.db import engine
from kernel.manifests import ADDRESSED, CAPABILITY_PATTERN, HUB, PLATFORM_SERVICES
from kernel.provision import MODULE_ID_PATTERN

router = APIRouter(tags=["capabilities"])

MODULE_HEADER = "x-arga-module"
TOKEN_HEADER = "x-module-token"

DECLARES = text("""
    select exists (
        select 1 from kernel.modules m
        where m.id = :module and m.enabled
          and coalesce(m.manifest->'uses', '[]'::jsonb) ? :capability
    )
""")


SERVED_BY = text("""
    select m.id from kernel.modules m
    where m.enabled and coalesce(m.manifest->'provides', '[]'::jsonb) ? :capability
      and (cast(:target as text) is null or m.id = :target)
    order by m.id
    limit 1
""")

TARGET_HEADER = "x-arga-target"


def module_url(module_id: str) -> str:
    template = os.environ.get("MODULE_URL_TEMPLATE", "http://{module}:8000")
    return template.format(module=module_id).rstrip("/")


def module_transport() -> httpx.AsyncBaseTransport | None:
    return None


def hub_url() -> str:
    return os.environ.get("HUB_URL", f"http://{HUB}:8000").rstrip("/")


def hub_timeout() -> float:
    return float(os.environ.get("CAPABILITY_TIMEOUT_SECONDS", "120"))


def hub_transport() -> httpx.AsyncBaseTransport | None:
    return None


_shared: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None


def shared_client() -> httpx.AsyncClient:
    global _shared
    loop = asyncio.get_running_loop()
    if _shared is None or _shared[0] is not loop or _shared[1].is_closed:
        _shared = (loop, httpx.AsyncClient(timeout=hub_timeout()))
    return _shared[1]


@router.post("/internal/capabilities/{capability}")
async def ask_for(
    capability: Annotated[str, PathParam(pattern=CAPABILITY_PATTERN)],
    request: Request,
    x_arga_module: Annotated[str, Header(pattern=MODULE_ID_PATTERN)],
    x_arga_target: Annotated[str | None, Header(pattern=MODULE_ID_PATTERN)] = None,
) -> Response:
    require_person()
    addressed = capability in ADDRESSED
    if addressed and not x_arga_target:
        raise HTTPException(
            status_code=422, detail=f"'{capability}' se pide a una app: falta {TARGET_HEADER}"
        )
    async with engine().connect() as connection:
        declared = await connection.scalar(
            DECLARES, {"module": x_arga_module, "capability": capability}
        )
        provider = await connection.scalar(
            SERVED_BY, {"capability": capability, "target": x_arga_target if addressed else None}
        )
    if not declared:
        raise HTTPException(
            status_code=403,
            detail=f"'{x_arga_module}' no declara '{capability}' en `uses` de su manifiesto",
        )
    if addressed and provider is None:
        raise HTTPException(status_code=404, detail=f"'{x_arga_target}' no sirve '{capability}'")
    if capability in PLATFORM_SERVICES:
        try:
            payload = json.loads(await request.body() or b"{}")
            answer = await notifications.serve(capability, x_arga_module, payload)
        except (ValueError, ValidationError) as error:
            raise HTTPException(status_code=422, detail=str(error)[:500]) from error
        return JSONResponse(answer)
    token = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="el kernel no tiene MODULE_REGISTRATION_TOKEN")

    if provider is None:
        base, transport, who = hub_url(), hub_transport(), "Hub"
    else:
        base, transport, who = module_url(provider), module_transport(), provider

    sent = {
        "content": await request.body(),
        "headers": {
            "content-type": "application/json",
            TOKEN_HEADER: token,
            MODULE_HEADER: x_arga_module,
            **user_headers(),
        },
    }
    try:
        if transport is None:
            answer = await shared_client().post(f"{base}/capabilities/{capability}", **sent)
        else:
            async with httpx.AsyncClient(
                base_url=base, transport=transport, timeout=hub_timeout()
            ) as target:
                answer = await target.post(f"/capabilities/{capability}", **sent)
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503, detail=f"{who} no contesta ({type(error).__name__})"
        ) from error
    return Response(
        content=answer.content,
        status_code=answer.status_code,
        media_type=answer.headers.get("content-type", "application/json"),
    )
