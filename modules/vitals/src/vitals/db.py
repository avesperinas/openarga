from __future__ import annotations

import os
from functools import cache

from sqlalchemy.ext.asyncio import AsyncEngine

from arga_tenancy import engine_for

SCHEMA = "vitals"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "falta DATABASE_URL. El módulo no arranca sin ella: servir sin base de datos "
            "es prometer un dato que no se tiene."
        )
    return url


@cache
def engine() -> AsyncEngine:
    return engine_for(database_url())
