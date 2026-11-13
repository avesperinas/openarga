from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hub import catalogue, credentials, rules
from hub.extractors import EXTRACTORS
from hub.sync import CLIENTS, NORMALISE, SETTINGS, used_today
from hub.words import say

WARNING = timedelta(days=14)
FAILURES = 2

State = Literal["pending", "paused", "expired", "expiring", "failing", "active"]


@dataclass(frozen=True)
class Connection:
    id: UUID
    provider: str
    label: str
    category: str
    state: State
    reason: str | None
    consent_expires_at: datetime | None
    last_ok_at: datetime | None
    last_run_at: datetime | None
    emitted_week: int


def state_of(
    status: str,
    paused: bool,
    expires: datetime | None,
    recent: list[str],
    now: datetime,
    missing: bool = False,
    empty: bool = False,
) -> State:
    if status == "pending":
        return "pending"
    if paused:
        return "paused"
    if missing:
        return "pending"
    if expires is not None and expires <= now:
        return "expired"
    if empty:
        return "failing"
    if expires is not None and expires - now <= WARNING:
        return "expiring"
    finished = [outcome for outcome in recent if outcome not in ("running", "skipped")]
    if len(finished) >= FAILURES and all(o == "error" for o in finished[:FAILURES]):
        return "failing"
    return "active"


def reason_of(
    label: str,
    state: State,
    expires: datetime | None,
    detail: str | None,
    now: datetime,
    missing: bool = False,
    empty: bool = False,
) -> str | None:
    if state == "pending" and missing:
        return say("connection.reason.missing", label=label)
    if state == "pending":
        return say("connection.reason.pending", label=label)
    if state == "expired" and expires is not None:
        return say("connection.reason.expired", label=label, date=expires.date().isoformat())
    if state == "expiring" and expires is not None:
        days = max(0, (expires - now).days)
        key = "connection.reason.expiring.one" if days == 1 else "connection.reason.expiring.other"
        return say(key, label=label, days=days)
    if state == "failing" and empty:
        return say("connection.reason.no_accounts", label=label)
    if state == "failing":
        if detail:
            return say("connection.reason.failing_detail", label=label, detail=detail)
        return say("connection.reason.failing", label=label)
    return None


LIST = text("""
    select c.id, c.provider, c.label, c.status, c.paused, c.consent_expires_at,
           coalesce(recent.outcomes, '{}') as outcomes, recent.detail, recent.last_run_at,
           (select max(finished_at) from hub.hub_run
            where connection_id = c.id and outcome = 'ok') as last_ok_at,
           (select coalesce(sum(emitted), 0) from hub.hub_run
            where connection_id = c.id and started_at >= :week) as emitted_week,
           (select coalesce(array_agg(key), '{}') from hub.hub_credential
            where connection_id = c.id) as keys,
           case jsonb_typeof(c.config->'accounts')
               when 'array' then jsonb_array_length(c.config->'accounts') else 0
           end as accounts
    from hub.hub_connection c
    left join lateral (
        select array_agg(outcome order by started_at desc) as outcomes,
               (array_agg(detail order by started_at desc))[1] as detail,
               max(started_at) as last_run_at
        from (
            select outcome, detail, started_at from hub.hub_run
            where connection_id = c.id
            order by started_at desc limit 5
        ) latest
    ) recent on true
    order by c.created_at
""")


async def listed(connection: AsyncConnection, now: datetime | None = None) -> list[Connection]:
    now = now or datetime.now(UTC)
    found = []
    for row in await connection.execute(LIST, {"week": now - timedelta(days=7)}):
        known = catalogue.BY_ID.get(row.provider)
        missing = known is not None and any(secret.key not in row.keys for secret in known.secrets)
        empty = known is not None and known.authorizes and row.accounts == 0
        state = state_of(
            row.status, row.paused, row.consent_expires_at, list(row.outcomes), now, missing, empty
        )
        found.append(
            Connection(
                id=row.id,
                provider=row.provider,
                label=row.label,
                category=known.category if known else "",
                state=state,
                reason=reason_of(
                    row.label, state, row.consent_expires_at, row.detail, now, missing, empty
                ),
                consent_expires_at=row.consent_expires_at,
                last_ok_at=row.last_ok_at,
                last_run_at=row.last_run_at,
                emitted_week=int(row.emitted_week),
            )
        )
    return found


URGENCY: dict[State, int] = {
    "expired": 0,
    "failing": 1,
    "expiring": 2,
    "pending": 3,
    "paused": 4,
    "active": 5,
}


def brief(state: State) -> str:
    return say(f"connection.brief.{state}")


TONE: dict[State, str] = {
    "expired": "negative",
    "failing": "negative",
    "expiring": "warning",
    "pending": "warning",
    "paused": "neutral",
    "active": "positive",
}


def needs_attention(item: Connection) -> bool:
    return item.state in ("expired", "failing", "expiring", "pending")


class Refused(ValueError):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def clean_secret(provider: catalogue.Provider, key: str, raw: str) -> str:
    secret = next(
        (item for item in provider.secrets if item.key == key), catalogue.Secret(key, key, key)
    )
    value = raw.strip()
    if not value:
        raise Refused(f"Falta {secret.label.lower()}")
    if len(value) > credentials.MAX_LENGTH:
        raise Refused(f"{secret.label}: too long")
    client = CLIENTS.get(provider.id)
    normalise = client.normalise if client else NORMALISE.get(provider.id, lambda _k, raw: raw)
    try:
        return normalise(key, value)
    except ValueError as error:
        raise Refused(f"{secret.label}: {error}") from error


def clean_secrets(
    provider: catalogue.Provider, raw: dict[str, str], partial: bool = False
) -> dict[str, str]:
    wanted = [secret.key for secret in provider.secrets]
    allowed = wanted + list(provider.internal if partial else ())
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise Refused(f"{provider.name} does not ask for {', '.join(unknown)}")
    return {
        key: clean_secret(provider, key, raw.get(key) or "")
        for key in allowed
        if not partial or (raw.get(key) or "").strip()
    }


def clean_label(provider: catalogue.Provider, label: str | None) -> str:
    cleaned = " ".join((label or "").split()) or provider.name
    if len(cleaned) > 80:
        raise Refused("The name cannot be longer than 80 characters")
    return cleaned


LABELS = text("""
    select id, label from hub.hub_connection where provider = :provider
""")


async def free_label(
    database: AsyncConnection,
    provider: catalogue.Provider,
    label: str | None,
    besides: UUID | None = None,
) -> str:
    cleaned = clean_label(provider, label)
    if not provider.unique_label:
        return cleaned
    for row in await database.execute(LABELS, {"provider": provider.id}):
        if row.id != besides and row.label.casefold() == cleaned.casefold():
            raise Refused(f"You already have a {provider.name} account called '{row.label}'", 409)
    return cleaned


FIRST_OF = text("""
    select id from hub.hub_connection
    where provider = :provider order by created_at limit 1
""")

INSERT = text("""
    insert into hub.hub_connection
        (id, provider, label, config, consent_expires_at, plugs)
    values (coalesce(:id, gen_random_uuid()), :provider, :label, cast(:config as jsonb), :consent,
            cast(:plugs as jsonb))
    returning id
""")


async def first_of(database: AsyncConnection, provider: str) -> UUID | None:
    return await database.scalar(FIRST_OF, {"provider": provider})


OTHERS_OF = text("""
    select id from hub.hub_connection
    where provider = :provider and id <> :id
    order by created_at
""")


async def share(database: AsyncConnection, provider: catalogue.Provider, created: UUID) -> int:
    copied = 0
    for key in provider.shared:
        if await credentials.use(database, provider.id, created, key):
            continue
        for other in (
            await database.execute(OTHERS_OF, {"provider": provider.id, "id": created})
        ).scalars():
            value = await credentials.use(database, provider.id, other, key)
            if value:
                await credentials.store(database, provider.id, created, key, value)
                copied += 1
                break
    return copied


async def create(
    database: AsyncConnection,
    provider_id: str,
    label: str | None,
    secrets: dict[str, str],
    *,
    connection_id: UUID | None = None,
    from_app: str | None = None,
    config: dict[str, Any] | None = None,
    consent_expires_at: datetime | None = None,
    plugs: dict[str, dict[str, Any]] | None = None,
) -> UUID:
    try:
        provider = catalogue.provider(provider_id)
    except LookupError as error:
        raise Refused(str(error), 404) from error
    if not provider.available:
        where = catalogue.APPS.get(provider.lives_in or "")
        raise Refused(
            f"{provider.name} is still configured in {where}"
            if where
            else f"{provider.name} cannot be connected yet",
            409,
        )
    if provider.created_in and from_app != provider.created_in:
        app = catalogue.APPS.get(provider.created_in, provider.created_in)
        raise Refused(f"{provider.name} connections are created from {app}", 409)
    if provider.authorizes and from_app is None:
        raise Refused(f"{provider.name} connects by authorising it, not with a key", 409)
    name = await free_label(database, provider, label)
    cleaned = clean_secrets(provider, secrets, partial=from_app is not None)
    if provider.settings and from_app is None:
        clean = (
            CLIENTS[provider.id].settings if provider.id in CLIENTS else SETTINGS.get(provider.id)
        )
        try:
            config = {**(config or {}), **(clean(config or {}) if clean else {})}
        except ValueError as error:
            raise Refused(str(error)) from error
    if provider.single and await first_of(database, provider.id) is not None:
        raise Refused(f"{provider.name} is already connected: change its key in its page", 409)
    created = await database.scalar(
        INSERT,
        {
            "id": connection_id,
            "provider": provider.id,
            "label": name,
            "config": json.dumps(config or {}),
            "consent": consent_expires_at,
            "plugs": json.dumps(plugs or {}),
        },
    )
    for key, value in cleaned.items():
        await credentials.store(database, provider.id, created, key, value)
    return created


RUNS = text("""
    select operation, started_at, finished_at, outcome, emitted, detail
    from hub.hub_run
    where connection_id = :id
    order by started_at desc
    limit :limit
""")


async def detail(
    database: AsyncConnection, connection_id: UUID, runs: int = 20, now: datetime | None = None
) -> dict | None:
    found = next((item for item in await listed(database, now) if item.id == connection_id), None)
    if found is None:
        return None
    provider = catalogue.BY_ID.get(found.provider)
    row = (
        await database.execute(
            text("select paused, config, plugs from hub.hub_connection where id = :id"),
            {"id": connection_id},
        )
    ).one()
    paused, config = row.paused, row.config or {}
    statuses = (
        await credentials.status(
            database, connection_id, tuple(secret.key for secret in provider.secrets)
        )
        if provider
        else []
    )
    labels = {secret.key: secret for secret in provider.secrets} if provider else {}
    return {
        **summary(found),
        "provider_name": provider.name if provider else found.provider,
        "paused": paused,
        "emits": list(provider.emits) if provider else [],
        "plugs": row.plugs or {},
        "secrets": [
            {
                "key": status.key,
                "label": labels[status.key].label,
                "help": labels[status.key].help,
                "multiline": labels[status.key].multiline,
                "configured": status.configured,
                "hint": status.hint,
                "created_at": status.created_at,
                "last_used_at": status.last_used_at,
            }
            for status in statuses
        ],
        "runs": [
            dict(run._mapping)
            for run in await database.execute(RUNS, {"id": connection_id, "limit": runs})
        ],
        "authorizes": bool(provider and (provider.authorizes or provider.oauth)),
        "push": bool(provider and "push" in provider.capabilities),
        "accounts": [
            {"name": item.get("name"), "iban_tail": item.get("iban_tail"), "kind": item.get("kind")}
            for item in config.get("accounts") or []
        ],
        "budget": await budget(database, provider, connection_id) if provider else None,
        "settings": {
            setting.key: config.get(setting.key)
            for setting in (provider.settings if provider else ())
        },
        "extractors": [
            {"id": extractor.id, "entity": extractor.entity} for extractor in EXTRACTORS.values()
        ]
        if provider and provider.id == "imap"
        else [],
        "rules": rules.of(config) if provider and provider.id == "imap" else [],
        **({"relay": config.get("relay", True) is not False} if found.provider == "claude" else {}),
    }


SET_RELAY = text("""
    update hub.hub_connection
    set config = jsonb_set(config, '{relay}', to_jsonb(cast(:relay as boolean)))
    where id = :id and provider = 'claude'
    returning id
""")


async def set_relay(database: AsyncConnection, connection_id: UUID, relay: bool) -> bool:
    return await database.scalar(SET_RELAY, {"id": connection_id, "relay": relay}) is not None


SET_RULES = text("""
    update hub.hub_connection
    set config = jsonb_set(config, '{rules}', cast(:rules as jsonb))
    where id = :id and provider = 'imap'
    returning id
""")


async def set_rules(database: AsyncConnection, connection_id: UUID, raw: list[Any]) -> bool:
    try:
        cleaned = rules.clean_all(raw)
    except rules.Invalid as error:
        raise Refused(str(error)) from error
    found = await database.scalar(SET_RULES, {"id": connection_id, "rules": json.dumps(cleaned)})
    return found is not None


CONFIG = text("select config from hub.hub_connection where id = :id")


async def config_of(database: AsyncConnection, connection_id: UUID) -> dict[str, Any]:
    return (await database.scalar(CONFIG, {"id": connection_id})) or {}


async def budget(
    database: AsyncConnection, provider: catalogue.Provider, connection_id: UUID
) -> dict | None:
    if provider.daily_budget is None:
        return None
    used = await used_today(database, connection_id)
    return {
        "limit": provider.daily_budget,
        "used": used,
        "remaining": max(0, provider.daily_budget - used),
    }


def summary(item: Connection) -> dict:
    return {
        "id": str(item.id),
        "provider": item.provider,
        "label": item.label,
        "category": item.category,
        "state": item.state,
        "brief": brief(item.state),
        "tone": TONE[item.state],
        "reason": item.reason,
        "consent_expires_at": item.consent_expires_at,
        "last_ok_at": item.last_ok_at,
        "last_run_at": item.last_run_at,
        "emitted_week": item.emitted_week,
    }


async def set_paused(database: AsyncConnection, connection_id: UUID, paused: bool) -> bool:
    result = await database.execute(
        text("update hub.hub_connection set paused = :paused where id = :id"),
        {"id": connection_id, "paused": paused},
    )
    return result.rowcount == 1


async def rename(database: AsyncConnection, connection_id: UUID, label: str) -> bool:
    provider_id = await database.scalar(
        text("select provider from hub.hub_connection where id = :id"),
        {"id": connection_id},
    )
    if provider_id is None:
        return False
    name = await free_label(database, catalogue.provider(provider_id), label, besides=connection_id)
    await database.execute(
        text("update hub.hub_connection set label = :label where id = :id"),
        {"id": connection_id, "label": name},
    )
    return True


async def remove(database: AsyncConnection, connection_id: UUID) -> bool:
    result = await database.execute(
        text("delete from hub.hub_connection where id = :id"), {"id": connection_id}
    )
    return result.rowcount == 1
