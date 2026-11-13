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
            "DATABASE_URL is missing. The module does not start without it: serving without a "
            "database would promise data it does not have."
        )
    return url


@cache
def engine() -> AsyncEngine:
    return engine_for(database_url())
