from __future__ import annotations

import json
import secrets as tokens
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from hub import catalogue, connections, credentials
from hub.banks import public_url
from hub.connections import Refused
from hub.providers import SourceError
from hub.providers import google_health as gh

PROVIDER = "google_health"


class UnknownAuthorisation(Exception):
    pass


def redirect_url() -> str:
    return f"{public_url()}/hub/google/callback"


EXISTING = text("""
    select id from hub.hub_connection where provider = 'google_health' limit 1
""")

INSERT = text("""
    insert into hub.hub_connection (provider, label, status, auth_state, config)
    values ('google_health', :label, 'pending', :state, '{}'::jsonb)
    returning id
""")


async def start(
    database: AsyncConnection, label: str | None, given: dict[str, str]
) -> tuple[UUID, str]:
    provider = catalogue.provider(PROVIDER)
    if await database.scalar(EXISTING) is not None:
        raise Refused(
            "Ya tienes Google Health conectado: para volver a autorizarlo, pulsa Reconectar en su "
            "ficha.",
            409,
        )
    cleaned = connections.clean_secrets(provider, given)
    state = tokens.token_urlsafe(32)
    connection_id = await database.scalar(
        INSERT, {"label": connections.clean_label(provider, label), "state": state}
    )
    for key, value in cleaned.items():
        await credentials.store(database, PROVIDER, connection_id, key, value)
    app = gh.App(cleaned[gh.CLIENT_ID], cleaned[gh.CLIENT_SECRET])
    return connection_id, gh.authorization_url(app, state, redirect_url())


async def app_of(database: AsyncConnection, connection_id: UUID) -> gh.App:
    found = {
        key: await credentials.use(database, PROVIDER, connection_id, key)
        for key in (gh.CLIENT_ID, gh.CLIENT_SECRET)
    }
    if not all(found.values()):
        raise Refused("No se puede abrir tu cliente de Google: vuelve a pegar el id y el secret")
    return gh.App(found[gh.CLIENT_ID] or "", found[gh.CLIENT_SECRET] or "")


async def reauthorize(database: AsyncConnection, connection_id: UUID) -> str:
    exists = await database.scalar(
        text("select id from hub.hub_connection where id = :id and provider = 'google_health'"),
        {"id": connection_id},
    )
    if exists is None:
        raise Refused("esa conexión no es Google Health", 404)
    app = await app_of(database, connection_id)
    state = tokens.token_urlsafe(32)
    await database.execute(
        text("update hub.hub_connection set auth_state = :state where id = :id"),
        {"state": state, "id": connection_id},
    )
    return gh.authorization_url(app, state, redirect_url())


PENDING = text("""
    select id from hub.hub_connection
    where auth_state = :state and provider = 'google_health'
""")

FINISH = text("""
    update hub.hub_connection
    set status = 'active', auth_state = null, consent_expires_at = null,
        config = config || cast(:config as jsonb)
    where id = :id
""")


async def finish(
    database: AsyncConnection, client: httpx.AsyncClient, state: str, code: str
) -> UUID:
    connection_id = await database.scalar(PENDING, {"state": state})
    if connection_id is None:
        raise UnknownAuthorisation
    app = await app_of(database, connection_id)
    try:
        refresh = await gh.exchange(client, app, code, redirect_url())
    except SourceError as error:
        raise Refused(str(error), 409) from error
    await credentials.store(database, PROVIDER, connection_id, gh.REFRESH, refresh)
    await database.execute(
        FINISH,
        {
            "id": connection_id,
            "config": json.dumps({"authorized_at": datetime.now(UTC).isoformat()}),
        },
    )
    return connection_id
