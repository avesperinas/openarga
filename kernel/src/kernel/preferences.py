from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["preferences"])

Locale = Literal["en", "es"]


class Preferences(BaseModel):
    locale: Locale
    timezone: str
    currency: str
    country: str | None
    region: str | None
    area: str | None


def instance_defaults() -> Preferences:
    locale = os.environ.get("OPENARGA_LOCALE", "en")
    return Preferences(
        locale=locale if locale in ("en", "es") else "en",
        timezone=os.environ.get("OPENARGA_TIMEZONE", "UTC"),
        currency=os.environ.get("OPENARGA_CURRENCY", "EUR"),
        country=os.environ.get("OPENARGA_COUNTRY") or None,
        region=os.environ.get("OPENARGA_REGION") or None,
        area=os.environ.get("OPENARGA_AREA") or None,
    )


@router.get("/me/preferences")
async def my_preferences() -> Preferences:
    return instance_defaults()
