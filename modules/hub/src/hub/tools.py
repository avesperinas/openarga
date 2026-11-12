from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import kernel_url
from hub import capabilities, catalogue, connections, instruments, statements, sync
from hub.funds import symbol_of

MODULE = "hub"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[[AsyncConnection, Any], Awaitable[dict[str, Any]]]


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


def when(moment) -> str | None:
    return moment.isoformat() if moment else None


async def get_connections(connection: AsyncConnection, _: NoArguments) -> dict[str, Any]:
    names = {category.id: category.name for category in catalogue.CATEGORIES}
    found = await connections.listed(connection)
    return {
        "connections": [
            {
                "name": item.label,
                "provider": catalogue.BY_ID[item.provider].name
                if item.provider in catalogue.BY_ID
                else item.provider,
                "category": names.get(item.category, item.category),
                "state": item.state,
                "reason": item.reason,
                "last_ok_at": when(item.last_ok_at),
                "consent_expires_at": when(item.consent_expires_at),
                "events_last_week": item.emitted_week,
            }
            for item in found
        ],
        "configured_elsewhere": sorted(
            {
                f"{provider.name}: en {catalogue.APPS[provider.lives_in]}"
                for provider in catalogue.PROVIDERS
                if provider.lives_in
            }
        ),
    }


class FundIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    value: Decimal | None = Field(default=None, ge=0)
    weight: Decimal | None = Field(default=None, ge=0, le=100)
    quantity: Decimal | None = Field(default=None, ge=0)
    price: Decimal | None = Field(default=None, gt=0)
    isin: str | None = Field(default=None, min_length=12, max_length=12)
    mic: str | None = Field(default=None, pattern=r"^[A-Z]{4}$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{2}[A-Za-z]$")


class PortfolioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str = Field(min_length=1, max_length=80)
    product: str = Field(min_length=1, max_length=120)
    on: date
    value: Decimal = Field(gt=0)
    contributed: Decimal | None = None
    funds: list[FundIn] = Field(min_length=1, max_length=60)


KINDS = {"fund": "fondo", "listed": "cotizado"}


def catalogued(fund: FundIn) -> str | None:
    if fund.mic or fund.currency:
        return None
    if fund.isin:
        known = instruments.in_catalogue(fund.isin.upper())
        return known.symbol if known else None
    return symbol_of(fund.name)


async def lines_of(
    funds: list[FundIn], on: date
) -> tuple[dict[int, instruments.Line], dict[int, str]]:
    found: dict[int, instruments.Line] = {}
    why: dict[int, str] = {}
    async with httpx.AsyncClient(transport=capabilities.source_transport()) as source:
        for index, fund in enumerate(funds):
            if catalogued(fund) is not None:
                continue
            try:
                found[index] = await instruments.resolve(
                    source,
                    name=fund.name,
                    since=on,
                    isin=fund.isin,
                    mic=fund.mic,
                    currency=fund.currency,
                )
            except instruments.Unresolved as error:
                why[index] = str(error)
    return found, why


async def record_portfolio(connection: AsyncConnection, request: PortfolioIn) -> dict[str, Any]:
    lines, why = await lines_of(request.funds, request.on)
    try:
        found = statements.portfolio(
            request.entity,
            request.product,
            request.on,
            request.value,
            request.contributed,
            [
                statements.Shown(
                    fund.name,
                    value=fund.value,
                    weight=fund.weight / 100 if fund.weight is not None else None,
                    quantity=fund.quantity,
                    price=fund.price,
                    line=lines.get(index),
                    unpriced=why.get(index),
                    symbol=catalogued(fund),
                )
                for index, fund in enumerate(request.funds)
            ],
        )
    except statements.StatementError as error:
        return {"recorded": False, "problem": str(error)}
    priced = list(lines.values())
    outcome = sync.Outcome(UUID(int=0), "ok")
    async with httpx.AsyncClient(
        base_url=kernel_url(), transport=capabilities.kernel_transport(), timeout=30.0
    ) as kernel:
        await sync.publish_all(kernel, statements.SOURCE, statements.events_of(found), outcome)
    unpriced = list(found.skipped)
    if priced and not await instruments.remember(connection, priced):
        unpriced += [
            f"«{line.name}»: conecta «Precios de fondos» en Hub para valorarlo cada día"
            for line in priced
        ]
    return {
        "recorded": True,
        "product": request.product,
        "on": request.on.isoformat(),
        "funds": len(found.holdings),
        "new": outcome.emitted,
        "repeated": outcome.duplicated,
        "priced_by_isin": [
            f"«{request.funds[index].name}»: {line.isin} ({KINDS[line.kind]}, {line.where}), "
            f"con precio desde el {request.on:%d/%m/%Y}"
            for index, line in lines.items()
        ],
        "without_price": unpriced,
    }


TOOLS: dict[str, Tool] = {
    "get_connections": Tool(NoArguments, get_connections),
    "record_portfolio": Tool(PortfolioIn, record_portfolio),
}
