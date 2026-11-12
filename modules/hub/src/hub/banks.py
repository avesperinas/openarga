from __future__ import annotations

import json
import os
import secrets as tokens
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hub import catalogue, connections, credentials
from hub.connections import Refused
from hub.providers import enable_banking as eb

PROVIDER = "enable_banking"


def public_url() -> str:
    return os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")


def redirect_url() -> str:
    return f"{public_url()}/hub/callback"


class UnknownAuthorisation(Exception):
    pass


def failure(error: eb.BankError) -> Refused:
    if error.code == eb.REDIRECT_NOT_ALLOWED:
        return Refused(
            f"Tu aplicación de Enable Banking no deja volver a {redirect_url()}. Añádela en su "
            "panel como dirección de vuelta (Redirect URLs) y prueba otra vez.",
            409,
        )
    return Refused(
        f"El banco contesta {error.status} {error.code}: {error.message}",
        503 if error.transient else 409,
    )


WITH_APP = text("""
    select c.id from hub.hub_connection c
    where c.provider = 'enable_banking'
      and (select count(*) from hub.hub_credential k
           where k.connection_id = c.id and k.key in ('app_id', 'private_key')) = 2
    order by c.created_at
    limit 1
""")


async def has_app(database: AsyncConnection) -> bool:
    return await database.scalar(WITH_APP) is not None


async def app_secrets(database: AsyncConnection, given: dict[str, str]) -> dict[str, str]:
    provider = catalogue.provider(PROVIDER)
    if any((value or "").strip() for value in given.values()):
        return connections.clean_secrets(provider, given)
    existing = await database.scalar(WITH_APP)
    if existing is None:
        raise Refused("Pega antes el id y la clave privada de tu aplicación de Enable Banking")
    found = {
        key: await credentials.use(database, PROVIDER, existing, key) for key in provider.shared
    }
    if not all(found.values()):
        raise Refused("No se puede abrir tu aplicación de Enable Banking: vuelve a pegarla")
    return {key: value for key, value in found.items() if value}


def api(client: httpx.AsyncClient, app: dict[str, str]) -> eb.EnableBanking:
    return eb.EnableBanking(client, eb.App(app[eb.APP_ID], app[eb.PRIVATE_KEY]))


async def banks(
    database: AsyncConnection, client: httpx.AsyncClient, country: str, given: dict[str, str]
) -> list[str]:
    try:
        return sorted(
            bank["name"]
            for bank in await api(client, await app_secrets(database, given)).banks(country)
        )
    except eb.BankError as error:
        raise failure(error) from error


async def _bank(client: httpx.AsyncClient, app: dict[str, str], bank: str, country: str) -> dict:
    found = next((b for b in await api(client, app).banks(country) if b["name"] == bank), None)
    if found is None:
        raise Refused(f"Enable Banking no conoce '{bank}' en {country}", 404)
    return found


INSERT = text("""
    insert into hub.hub_connection (provider, label, status, auth_state, config)
    values ('enable_banking', :label, 'pending', :state, cast(:config as jsonb))
    returning id
""")


async def start(
    database: AsyncConnection,
    client: httpx.AsyncClient,
    bank: str,
    country: str,
    label: str | None,
    given: dict[str, str],
    now: datetime | None = None,
) -> tuple[UUID, str]:
    app = await app_secrets(database, given)
    try:
        found = await _bank(client, app, bank, country)
        state = tokens.token_urlsafe(32)
        connection_id = await database.scalar(
            INSERT,
            {
                "label": connections.clean_label(catalogue.provider(PROVIDER), label or bank),
                "state": state,
                "config": json.dumps({"bank": bank, "country": country}),
            },
        )
        for key, value in app.items():
            await credentials.store(database, PROVIDER, connection_id, key, value)
        url = await api(client, app).authorise(
            bank, country, eb.validity_for(found, now or datetime.now(UTC)), state, redirect_url()
        )
    except eb.BankError as error:
        raise failure(error) from error
    return connection_id, url


BANK_OF = text("""
    select id, config from hub.hub_connection
    where id = :id and provider = 'enable_banking'
""")


async def reauthorize(
    database: AsyncConnection, client: httpx.AsyncClient, connection_id: UUID
) -> str:
    row = (await database.execute(BANK_OF, {"id": connection_id})).one_or_none()
    if row is None:
        raise Refused("esa conexión no es un banco", 404)
    app = await app_secrets(database, {})
    config = row.config or {}
    try:
        found = await _bank(client, app, config["bank"], config.get("country", "ES"))
        state = tokens.token_urlsafe(32)
        await database.execute(
            text("update hub.hub_connection set auth_state = :state where id = :id"),
            {"state": state, "id": connection_id},
        )
        return await api(client, app).authorise(
            config["bank"],
            config.get("country", "ES"),
            eb.validity_for(found, datetime.now(UTC)),
            state,
            redirect_url(),
        )
    except eb.BankError as error:
        raise failure(error) from error


PENDING = text("""
    select id, label, config from hub.hub_connection
    where auth_state = :state and provider = 'enable_banking'
""")

FINISH = text("""
    update hub.hub_connection
    set status = 'active', auth_state = null, consent_expires_at = :until,
        config = config || cast(:config as jsonb)
    where id = :id
""")


async def finish(
    database: AsyncConnection, client: httpx.AsyncClient, state: str, code: str
) -> tuple[UUID, dict[str, Any]]:
    row = (await database.execute(PENDING, {"state": state})).one_or_none()
    if row is None:
        raise UnknownAuthorisation
    app = await app_secrets(database, {})
    try:
        session = await api(client, app).open_session(code)
    except eb.BankError as error:
        raise failure(error) from error
    await credentials.store(database, PROVIDER, row.id, eb.SESSION, session["session_id"])
    config = {
        "accounts": [eb.account_of(raw) for raw in session.get("accounts") or []],
        "authorized_at": datetime.now(UTC).isoformat(),
    }
    await database.execute(
        FINISH,
        {
            "id": row.id,
            "until": datetime.fromisoformat(session["access"]["valid_until"]),
            "config": json.dumps(config),
        },
    )
    return row.id, {**(row.config or {}), **config}


def account_events(connection_id: UUID, config: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        eb.account_event(str(connection_id), config.get("bank", ""), account)
        for account in config.get("accounts") or []
    ]
