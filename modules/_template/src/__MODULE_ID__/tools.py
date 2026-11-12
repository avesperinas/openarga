from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from __MODULE_ID__ import readings

MODULE = "__MODULE_ID__"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


class GetReadings(BaseModel):
    label: str | None = Field(
        default=None, description="Solo las lecturas de esta etiqueta. Sin ella, todas."
    )
    limit: int = Field(default=30, ge=1, le=500, description="Cuántas lecturas, como mucho.")


async def get_readings(connection: AsyncConnection, arguments: GetReadings) -> dict[str, Any]:
    found = await readings.list_readings(connection, arguments.label, arguments.limit)
    return {
        "readings": [one.model_dump(mode="json", exclude={"id"}) for one in found],
        "targets": {one.label: one.value for one in await readings.targets(connection)},
    }


async def add_reading(connection: AsyncConnection, arguments: readings.ReadingIn) -> dict[str, Any]:
    return (await readings.add(connection, arguments)).model_dump(mode="json")


async def set_target(connection: AsyncConnection, arguments: readings.TargetIn) -> dict[str, Any]:
    return (await readings.set_target(connection, arguments)).model_dump(mode="json")


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[[AsyncConnection, Any], Awaitable[dict[str, Any]]]


TOOLS: dict[str, Tool] = {
    "get_readings": Tool(GetReadings, get_readings),
    "add_reading": Tool(readings.ReadingIn, add_reading),
    "set_target": Tool(readings.TargetIn, set_target),
}
