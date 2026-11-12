from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.db import database_url, engine

SCHEMA = "notebook"

__all__ = ["SCHEMA", "as_module", "database_url", "engine"]


@asynccontextmanager
async def as_module() -> AsyncIterator[AsyncConnection]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_notebook"'))
        yield connection
