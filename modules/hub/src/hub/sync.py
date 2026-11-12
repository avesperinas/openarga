from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_contracts import sources
from arga_tenancy import user_headers
from hub import catalogue, credentials
from hub.db import as_module
from hub.providers import Fetched, SourceError, claude, enable_banking

MODULE = "hub"
RUN = "hub.run"
ATTEMPTS = int(os.environ.get("WORKER_ATTEMPTS", "3"))
BACKOFF_SECONDS = float(os.environ.get("WORKER_BACKOFF_SECONDS", "30"))
BATCH = 200
DETAIL_LIMIT = 1000
MISSING_CREDENTIAL = "missing_credential"

Fetch = Callable[
    [httpx.AsyncClient, dict[str, str], Any], Awaitable["list[dict[str, Any]] | Fetched"]
]
ShouldRun = Callable[[AsyncConnection, Any, datetime], Awaitable[bool]]

LAST_OBSERVATION = text("""
    select ts, payload from hub.events
    where type in ('ai.claude.ping', 'ai.claude.usage') and payload->>'account_id' = :account
    order by ts desc
    limit 1
""")


async def claude_window_open(database: AsyncConnection, connection: Any, now: datetime) -> bool:
    row = (await database.execute(LAST_OBSERVATION, {"account": str(connection.id)})).first()
    return claude.usage_due(row.ts if row else None, row.payload if row else None, now)


USED_TODAY = text("""
    select count(*) from hub.hub_run
    where connection_id = :connection and capability = 'sync' and outcome <> 'skipped'
      and started_at >= date_trunc('day', now())
""")

LAST_TIMES = text("""
    select max(started_at) filter (where outcome = 'ok') as last_ok,
           max(started_at) filter (where outcome <> 'skipped') as last_attempt
    from hub.hub_run
    where connection_id = :connection and capability = 'sync'
""")


async def used_today(database: AsyncConnection, connection_id: UUID) -> int:
    return int(await database.scalar(USED_TODAY, {"connection": connection_id}) or 0)


def remaining(provider: catalogue.Provider, used: int) -> int | None:
    return None if provider.daily_budget is None else max(0, provider.daily_budget - used)


def when(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw) if raw else None


async def last_ok_of(database: AsyncConnection, connection: Any) -> datetime | None:
    times = (await database.execute(LAST_TIMES, {"connection": connection.id})).one()
    handed = when((connection.config or {}).get("synced_until"))
    candidates = [moment for moment in (times.last_ok, handed) if moment is not None]
    return max(candidates) if candidates else None


def consent_alive(connection: Any, now: datetime) -> bool:
    expires = getattr(connection, "consent_expires_at", None)
    return expires is None or expires > now


async def bank_due(database: AsyncConnection, connection: Any, now: datetime) -> bool:
    if not consent_alive(connection, now):
        return False
    if (
        remaining(
            catalogue.provider(connection.provider), await used_today(database, connection.id)
        )
        == 0
    ):
        return False
    last_ok = await last_ok_of(database, connection)
    return last_ok is None or now - last_ok >= enable_banking.MIN_INTERVAL


async def bank_urgent(database: AsyncConnection, connection: Any, now: datetime) -> bool:
    authorized = when((connection.config or {}).get("authorized_at"))
    if authorized is None or not consent_alive(connection, now):
        return False
    times = (await database.execute(LAST_TIMES, {"connection": connection.id})).one()
    if times.last_attempt is not None and times.last_attempt >= authorized:
        return False
    provider = catalogue.provider(connection.provider)
    return remaining(provider, await used_today(database, connection.id)) != 0


@dataclass(frozen=True)
class Client:
    operation: str
    fetch: Fetch
    normalise: Callable[[str, str], str]
    should_run: ShouldRun | None = None
    urgent: ShouldRun | None = None
    settings: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    recall: Callable[[AsyncConnection, Any], Awaitable[dict[str, Any]]] | None = None


POLICIES: dict[str, tuple[ShouldRun | None, ShouldRun | None]] = {
    "budget": (bank_due, bank_urgent),
    "open_window": (claude_window_open, None),
    "authorized": (None, bank_urgent),
}


def client_of(provider: catalogue.Provider) -> Client | None:
    if provider.sync is None:
        return None
    should_run, urgent = POLICIES.get(provider.sync.policy or "", (None, None))
    return Client(
        provider.sync.operation,
        provider.sync.fetch,
        provider.normalise,
        should_run,
        urgent,
        provider.clean,
        provider.sync.recall,
    )


CLIENTS: dict[str, Client] = {
    one.id: client for one in catalogue.PROVIDERS if (client := client_of(one)) is not None
}


@dataclass(frozen=True)
class Target:
    id: UUID
    provider: str
    label: str
    config: dict[str, Any]
    last_ok: datetime | None
    recalled: dict[str, Any] = field(default_factory=dict)


NORMALISE: dict[str, Callable[[str, str], str]] = {
    one.id: one.normalise for one in catalogue.PROVIDERS if one.sync is None
}
SETTINGS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    one.id: one.clean for one in catalogue.PROVIDERS if one.sync is None and one.clean is not None
}


@dataclass
class Outcome:
    run_id: UUID
    outcome: str
    emitted: int = 0
    duplicated: int = 0
    detail: str | None = None
    code: str | None = None
    key: str | None = None
    ran_on: str | None = None
    ran_with: str | None = None


START = text("""
    insert into hub.hub_run (connection_id, capability, operation, idempotency_key)
    values (:connection, :capability, :operation, :key)
    on conflict do nothing
    returning id
""")

FINISH = text("""
    update hub.hub_run
    set outcome = :outcome, finished_at = now(), emitted = :emitted, detail = :detail, code = :code
    where id = :id
    returning started_at, finished_at
""")


CODE = re.compile(r"[a-z][a-z0-9_]{1,40}")


def shorten(detail: str | None) -> str | None:
    return detail[:DETAIL_LIMIT] if detail else detail


async def start(
    database: AsyncConnection,
    connection_id: UUID,
    capability: str,
    operation: str,
    key: str | None = None,
) -> UUID | None:
    return await database.scalar(
        START,
        {"connection": connection_id, "capability": capability, "operation": operation, "key": key},
    )


async def secrets_of(
    database: AsyncConnection, provider: catalogue.Provider, connection_id: UUID
) -> dict[str, str | None]:
    keys = [secret.key for secret in provider.secrets] + list(provider.internal)
    return {key: await credentials.use(database, provider.id, connection_id, key) for key in keys}


def missing_credential(
    provider: catalogue.Provider, secrets: dict[str, str | None], result
) -> bool:
    missing = [secret.label for secret in provider.secrets if not secrets.get(secret.key)]
    if missing:
        result.outcome = "skipped"
        result.code = MISSING_CREDENTIAL
        result.detail = f"Falta la credencial ({', '.join(missing)}): pégala en la ficha."
    return bool(missing)


async def finish(
    kernel: httpx.AsyncClient,
    connection: Any,
    provider: str,
    capability: str,
    operation: str,
    result: Outcome,
) -> None:
    async with as_module() as database:
        times = (
            await database.execute(
                FINISH,
                {
                    "id": result.run_id,
                    "outcome": result.outcome,
                    "emitted": result.emitted,
                    "detail": shorten(result.detail),
                    "code": result.code if result.code and CODE.fullmatch(result.code) else None,
                },
            )
        ).one()
    await announce(kernel, connection, provider, capability, operation, result, times)


async def publish(kernel: httpx.AsyncClient, event: dict[str, Any]) -> bool:
    response = await kernel.post("/events", json=event, headers=user_headers())
    response.raise_for_status()
    return bool(response.json()["created"])


async def publish_all(
    kernel: httpx.AsyncClient, provider: str, events: list[dict[str, Any]], result: Outcome
) -> int:
    known = catalogue.BY_ID.get(provider)
    source = (known.source if known else None) or provider
    for event in events:
        if known is not None and event["type"] not in known.emits:
            raise sources.BadSource(f"{provider} no declara que produzca {event['type']}")
        sources.check(event["type"], event["payload"])
        sources.check_ts(event["type"], event["payload"], event["ts"])
    new_movements = 0
    stamped = [{**event, "module": MODULE, "source": source} for event in events]
    for start_at in range(0, len(stamped), BATCH):
        chunk = stamped[start_at : start_at + BATCH]
        for event, created in zip(chunk, await publish_batch(kernel, chunk), strict=True):
            if created:
                result.emitted += 1
                new_movements += event["type"] == enable_banking.MOVEMENT
            else:
                result.duplicated += 1
    return new_movements


async def publish_batch(kernel: httpx.AsyncClient, events: list[dict[str, Any]]) -> list[bool]:
    response = await kernel.post("/events/batch", json={"events": events}, headers=user_headers())
    if response.status_code in (404, 405):
        return [await publish(kernel, event) for event in events]
    response.raise_for_status()
    return [bool(one["created"]) for one in response.json()["results"]]


async def resolve_merchants(kernel: httpx.AsyncClient) -> None:
    try:
        response = await kernel.post("/resolution/run", headers=user_headers())
        response.raise_for_status()
    except httpx.HTTPError as error:
        print(f"la pasada de resolución no ha podido correr: {error}", file=sys.stderr)


CONSENT_OVER = text("""
    update hub.hub_connection set consent_expires_at = now()
    where id = :id and (consent_expires_at is null or consent_expires_at > now())
""")


REMEMBER = text("""
    update hub.hub_connection set config = config || cast(:config as jsonb)
    where id = :id
""")


def fetched(got: list[dict[str, Any]] | Fetched) -> Fetched:
    return got if isinstance(got, Fetched) else Fetched(got)


async def fetch(
    client: Client,
    source: httpx.AsyncClient,
    secrets: dict[str, str],
    connection: Any,
    attempts: int,
    sleep: Callable[[float], Awaitable[None]],
) -> Fetched:
    for number in range(1, attempts):
        try:
            return fetched(await client.fetch(source, secrets, connection))
        except SourceError as error:
            if not error.transient:
                raise
            await sleep(BACKOFF_SECONDS * number)
    return fetched(await client.fetch(source, secrets, connection))


async def run(
    connection: Any,
    *,
    source: httpx.AsyncClient,
    kernel: httpx.AsyncClient,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Outcome:
    provider = catalogue.provider(connection.provider)
    client = CLIENTS[provider.id]
    async with as_module() as database:
        target = Target(
            id=connection.id,
            provider=connection.provider,
            label=connection.label,
            config=getattr(connection, "config", None) or {},
            last_ok=await last_ok_of(database, connection)
            if hasattr(connection, "config")
            else None,
        )
        if client.recall is not None:
            target = replace(target, recalled=await client.recall(database, connection))
        run_id = await start(database, connection.id, "sync", client.operation)
        secrets = await secrets_of(database, provider, connection.id)

    result = Outcome(run_id, "ok")
    if not missing_credential(provider, secrets, result):
        try:
            got = await fetch(client, source, secrets, target, attempts, sleep)
            if await publish_all(kernel, provider.id, got.events, result):
                await resolve_merchants(kernel)
            if got.state:
                async with as_module() as database:
                    await database.execute(
                        REMEMBER, {"id": connection.id, "config": json.dumps(got.state)}
                    )
            result.detail = got.note
            if got.problem:
                result.outcome = "rate_limited" if got.rate_limited else "error"
                result.detail = got.problem
            elif got.config and result.outcome == "ok":
                async with as_module() as database:
                    await database.execute(
                        REMEMBER, {"id": connection.id, "config": json.dumps(got.config)}
                    )
        except SourceError as error:
            result.outcome = "rate_limited" if error.rate_limited else "error"
            result.detail = str(error)
            if error.code == "consent_over":
                async with as_module() as database:
                    await database.execute(CONSENT_OVER, {"id": connection.id})
                await announce_connection(
                    kernel,
                    {
                        "id": str(connection.id),
                        "provider": provider.id,
                        "label": connection.label,
                        "state": "expired",
                        "reason": f"{connection.label} cerró el acceso; hay que reconectarlo.",
                        "consent_expires_at": datetime.now(UTC),
                    },
                )
        except httpx.HTTPError as error:
            result.outcome = "error"
            result.detail = f"El kernel no aceptó lo traído: {type(error).__name__} {error}"
        except Exception as error:  # noqa: BLE001 - un cliente roto no tumba el worker
            result.outcome = "error"
            result.detail = f"{type(error).__name__}: {error}"

    await finish(kernel, connection, provider.id, "sync", client.operation, result)
    return result


async def announce(
    kernel: httpx.AsyncClient,
    connection: Any,
    provider: str,
    capability: str,
    operation: str,
    result: Outcome,
    times: Any,
) -> None:
    finished: datetime = times.finished_at
    event = {
        "ts": finished.isoformat(),
        "module": MODULE,
        "source": provider,
        "type": RUN,
        "payload": {
            "connection": str(connection.id),
            "provider": provider,
            "label": connection.label,
            "capability": capability,
            "operation": operation,
            "outcome": result.outcome,
            "code": result.code,
            "emitted": result.emitted,
            "detail": shorten(result.detail),
            "started_at": times.started_at.isoformat(),
            "finished_at": finished.isoformat(),
            **({"key": result.key} if result.key else {}),
            **({"ran_on": result.ran_on, "ran_with": result.ran_with} if result.ran_on else {}),
        },
        "dedup_hash": f"run:{result.run_id}",
    }
    try:
        await publish(kernel, event)
    except httpx.HTTPError as error:
        print(f"hub.run sin publicar ({type(error).__name__})", file=sys.stderr)


CONNECTION = "hub.connection"


async def announce_connection(
    kernel: httpx.AsyncClient, found: dict[str, Any], removed: bool = False
) -> None:
    now = datetime.now(UTC)
    event = {
        "ts": now.isoformat(),
        "module": MODULE,
        "source": found["provider"],
        "type": CONNECTION,
        "payload": {
            "connection": found["id"],
            "provider": found["provider"],
            "label": found["label"],
            "state": "removed" if removed else found["state"],
            "reason": None if removed else found.get("reason"),
            "consent_expires_at": _iso(found.get("consent_expires_at")),
            "paused": found.get("paused", False),
            "missing": [item["key"] for item in found.get("secrets", []) if not item["configured"]],
            "removed": removed,
            "produces": found.get("emits", []),
            "plugs": found.get("plugs", {}),
        },
        "dedup_hash": f"connection:{found['id']}:{now.isoformat()}",
    }
    try:
        await publish(kernel, event)
    except httpx.HTTPError as error:
        print(f"hub.connection sin publicar ({type(error).__name__})", file=sys.stderr)


def _iso(moment: datetime | str | None) -> str | None:
    return moment.isoformat() if isinstance(moment, datetime) else moment


async def publish_events(
    kernel: httpx.AsyncClient, provider: str, events: list[dict[str, Any]]
) -> None:
    try:
        await publish_all(kernel, provider, events, Outcome(UUID(int=0), "ok"))
    except httpx.HTTPError as error:
        print(f"{len(events)} eventos sin publicar ({type(error).__name__})", file=sys.stderr)
