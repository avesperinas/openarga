from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import available_timezones

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL, as_user, current_user, require_person
from kernel.db import engine

router = APIRouter(tags=["preferences"])

Locale = Literal["en", "es"]
FIELDS = ("locale", "timezone", "currency", "country", "region", "area")

Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Country = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
Region = Annotated[str, Field(pattern=r"^[A-Z]{2}-[A-Z0-9]{1,3}$")]
Area = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]


@lru_cache(maxsize=1)
def zones() -> frozenset[str]:
    return frozenset(available_timezones())


def known_zone(name: str) -> bool:
    return name in zones() or name == "UTC"


class Preferences(BaseModel):
    locale: Locale
    timezone: str
    currency: str
    country: str | None
    region: str | None
    area: str | None


class PreferencesIn(BaseModel):
    locale: Locale | None = None
    timezone: str | None = None
    currency: Currency | None = None
    country: Country | None = None
    region: Region | None = None
    area: Area | None = None

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str | None) -> str | None:
        if value is not None and not known_zone(value):
            raise ValueError(f"{value!r} is not an IANA time zone")
        return value

    @model_validator(mode="after")
    def _region_in_country(self) -> PreferencesIn:
        if self.region and self.country and not self.region.startswith(f"{self.country}-"):
            raise ValueError(f"region {self.region} is not in country {self.country}")
        return self


def instance_defaults() -> Preferences:
    locale = os.environ.get("OPENARGA_LOCALE", "en")
    zone = os.environ.get("OPENARGA_TIMEZONE", "UTC")
    return Preferences(
        locale=locale if locale in ("en", "es") else "en",
        timezone=zone if known_zone(zone) else "UTC",
        currency=os.environ.get("OPENARGA_CURRENCY", "EUR"),
        country=os.environ.get("OPENARGA_COUNTRY") or None,
        region=os.environ.get("OPENARGA_REGION") or None,
        area=os.environ.get("OPENARGA_AREA") or None,
    )


READ = text(f"""
    select locale, timezone, currency, country, region, area
    from kernel.person_preferences where user_id = {CURRENT_USER_SQL}
""")

WRITE = text("""
    insert into kernel.person_preferences
        (locale, timezone, currency, country, region, area, updated_at)
    values (:locale, :timezone, :currency, :country, :region, :area, now())
    on conflict (user_id) do update set
        locale = excluded.locale, timezone = excluded.timezone, currency = excluded.currency,
        country = excluded.country, region = excluded.region, area = excluded.area,
        updated_at = now()
""")


def effective(stored: dict[str, str | None] | None) -> Preferences:
    base = instance_defaults().model_dump()
    chosen = {key: value for key, value in (stored or {}).items() if value is not None}
    if chosen.get("timezone") and not known_zone(chosen["timezone"]):
        chosen.pop("timezone")
    return Preferences.model_validate({**base, **chosen})


async def stored_of(connection: AsyncConnection) -> dict[str, str | None] | None:
    row = (await connection.execute(READ)).mappings().first()
    return dict(row) if row is not None else None


async def of_person(connection: AsyncConnection) -> Preferences:
    if current_user.get() is None:
        return instance_defaults()
    return effective(await stored_of(connection))


async def of_user(user: UUID) -> Preferences:
    with as_user(user):
        async with engine().connect() as connection:
            return effective(await stored_of(connection))


@router.get("/me/preferences")
async def my_preferences() -> Preferences:
    if current_user.get() is None:
        return instance_defaults()
    async with engine().connect() as connection:
        return await of_person(connection)


@router.patch("/me/preferences")
async def change_preferences(body: PreferencesIn) -> Preferences:
    require_person()
    async with engine().begin() as connection:
        stored = await stored_of(connection) or dict.fromkeys(FIELDS)
        given = body.model_dump(include=body.model_fields_set)
        merged = {**stored, **given}
        if (
            merged["region"]
            and merged["country"]
            and not merged["region"].startswith(f"{merged['country']}-")
        ):
            merged["region"] = None
        await connection.execute(WRITE, merged)
        return effective(merged)
