from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_crypto import NotConfigured, Undecipherable, hint
from hub import credentials, fake
from hub.ai.providers import ANTHROPIC_MODELS, Anthropic, Fake, OpenAICompatible, Provider

ProviderName = Literal["none", "fake", "anthropic", "openai"]
Role = Literal["fast", "smart"]
KEY_NAME = "ai:key"

BaseUrl = Annotated[str, Field(pattern=r"^https?://", max_length=300)]
Model = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^\S+$")]


class Unavailable(Exception):
    pass


@dataclass(frozen=True)
class Effective:
    provider: ProviderName
    base_url: str | None
    fast_model: str | None
    smart_model: str | None
    monthly_tokens: int | None
    key: str | None

    def model(self, role: Role) -> str:
        if self.provider == "none":
            raise Unavailable("no AI provider is configured")
        chosen = self.fast_model if role == "fast" else self.smart_model
        if chosen:
            return chosen
        if self.provider == "anthropic":
            return ANTHROPIC_MODELS[role]
        if self.provider == "fake":
            return "fake"
        raise Unavailable(f"no model is set for the {role} role")


def instance() -> Effective:
    default = "fake" if fake.enabled() else "none"
    chosen = os.environ.get("OPENARGA_AI_PROVIDER", "").strip().lower() or default
    budget = os.environ.get("OPENARGA_AI_MONTHLY_TOKENS", "").strip()
    return Effective(
        provider=chosen if chosen in ("none", "fake", "anthropic", "openai") else "none",
        base_url=os.environ.get("OPENARGA_AI_BASE_URL", "").strip() or None,
        fast_model=os.environ.get("OPENARGA_AI_FAST_MODEL", "").strip() or None,
        smart_model=os.environ.get("OPENARGA_AI_SMART_MODEL", "").strip() or None,
        monthly_tokens=int(budget) if budget.isdigit() else None,
        key=os.environ.get("OPENARGA_AI_KEY", "").strip() or None,
    )


READ = text("""
    select provider, base_url, fast_model, smart_model, monthly_tokens,
           key_ciphertext, key_hint, updated_at
    from hub.ai_settings
""")

WRITE = text("""
    insert into hub.ai_settings (provider, base_url, fast_model, smart_model, monthly_tokens,
                                 updated_at)
    values (:provider, :base_url, :fast_model, :smart_model, :monthly_tokens, now())
    on conflict (user_id) do update set
        provider = excluded.provider, base_url = excluded.base_url,
        fast_model = excluded.fast_model, smart_model = excluded.smart_model,
        monthly_tokens = excluded.monthly_tokens, updated_at = now()
""")

WRITE_KEY = text("""
    insert into hub.ai_settings (key_ciphertext, key_hint, updated_at)
    values (:ciphertext, :hint, now())
    on conflict (user_id) do update set
        key_ciphertext = excluded.key_ciphertext, key_hint = excluded.key_hint,
        updated_at = now()
""")


class SettingsIn(BaseModel):
    provider: ProviderName | None = None
    base_url: BaseUrl | None = None
    fast_model: Model | None = None
    smart_model: Model | None = None
    monthly_tokens: Annotated[int, Field(ge=0)] | None = None


class SettingsOut(BaseModel):
    provider: ProviderName
    base_url: str | None
    fast_model: str | None
    smart_model: str | None
    monthly_tokens: int | None
    key_hint: str | None
    own_key: bool
    instance_key: bool
    mine: SettingsIn
    updated_at: datetime | None


async def stored(connection: AsyncConnection):
    return (await connection.execute(READ)).one_or_none()


def _key_of(row) -> str | None:
    if row is None or row.key_ciphertext is None:
        return None
    try:
        return credentials.vault("ai").open(credentials.person(), KEY_NAME, row.key_ciphertext)
    except (Undecipherable, NotConfigured):
        return None


async def effective(connection: AsyncConnection) -> Effective:
    base = instance()
    row = await stored(connection)
    if row is None:
        return base
    own_provider = row.provider is not None and row.provider != base.provider
    return replace(
        base,
        provider=row.provider or base.provider,
        base_url=row.base_url or (None if own_provider else base.base_url),
        fast_model=row.fast_model or (None if own_provider else base.fast_model),
        smart_model=row.smart_model or (None if own_provider else base.smart_model),
        monthly_tokens=row.monthly_tokens
        if row.monthly_tokens is not None
        else base.monthly_tokens,
        key=_key_of(row) or (None if own_provider else base.key),
    )


async def describe(connection: AsyncConnection) -> SettingsOut:
    row = await stored(connection)
    found = await effective(connection)
    mine = SettingsIn(
        provider=row.provider if row else None,
        base_url=row.base_url if row else None,
        fast_model=row.fast_model if row else None,
        smart_model=row.smart_model if row else None,
        monthly_tokens=row.monthly_tokens if row else None,
    )
    return SettingsOut(
        provider=found.provider,
        base_url=found.base_url,
        fast_model=found.fast_model,
        smart_model=found.smart_model,
        monthly_tokens=found.monthly_tokens,
        key_hint=row.key_hint if row is not None and row.key_ciphertext is not None else None,
        own_key=row is not None and row.key_ciphertext is not None,
        instance_key=instance().key is not None,
        mine=mine,
        updated_at=row.updated_at if row else None,
    )


async def save(connection: AsyncConnection, wanted: SettingsIn) -> None:
    await connection.execute(WRITE, wanted.model_dump())


async def save_key(connection: AsyncConnection, secret: str | None) -> None:
    if secret is None:
        await connection.execute(WRITE_KEY, {"ciphertext": None, "hint": None})
        return
    sealed = credentials.vault("ai").seal(credentials.person(), KEY_NAME, secret)
    await connection.execute(WRITE_KEY, {"ciphertext": sealed, "hint": hint(secret)})


def provider_for(
    found: Effective,
    client: httpx.AsyncClient,
    anthropic_client=None,
) -> Provider:
    if found.provider == "fake":
        return Fake()
    if found.provider == "anthropic":
        if not found.key:
            raise Unavailable("Anthropic needs an API key")
        return Anthropic(found.key, found.base_url, anthropic_client)
    if found.provider == "openai":
        if not found.base_url:
            raise Unavailable("an OpenAI-compatible provider needs its base URL")
        return OpenAICompatible(found.base_url, found.key, client)
    raise Unavailable("no AI provider is configured")
