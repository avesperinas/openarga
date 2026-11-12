from __future__ import annotations

import os
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from arga_tenancy import engine_for

DEFAULT_URL = "postgresql+asyncpg://openarga:changeme@localhost:5432/openarga"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


@lru_cache(maxsize=1)
def engine() -> AsyncEngine:
    return engine_for(database_url(), pool_size=5, max_overflow=5)


@lru_cache(maxsize=1)
def session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine(), expire_on_commit=False)


async def session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as active:
        yield active
