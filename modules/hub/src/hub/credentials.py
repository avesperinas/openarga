from __future__ import annotations

import os
from datetime import datetime
from functools import cache
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_crypto import NotConfigured, Undecipherable, Vault, decode_key, hint
from arga_tenancy import current_user

VARIABLE = "HUB_CREDENTIALS_KEY"
MAX_LENGTH = 8192


def _subkey(master: bytes, provider: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"arga:hub:{provider}".encode(),
    ).derive(master)


@cache
def masters() -> tuple[bytes, tuple[bytes, ...]]:
    raw = os.environ.get(VARIABLE, "").strip()
    if not raw:
        raise NotConfigured(f"falta {VARIABLE}: sin ella no se puede guardar ni usar ninguna")
    previous_raw = os.environ.get(f"{VARIABLE}_PREVIOUS", "").strip()
    previous = (decode_key(previous_raw, f"{VARIABLE}_PREVIOUS"),) if previous_raw else ()
    return decode_key(raw, VARIABLE), previous


def vault(provider: str) -> Vault:
    master, previous = masters()
    return Vault(
        f"hub:{provider}",
        _subkey(master, provider),
        tuple(_subkey(key, provider) for key in previous),
    )


def _name(connection_id: UUID, key: str) -> str:
    return f"{connection_id}:{key}"


class Status(BaseModel):
    key: str
    configured: bool
    hint: str | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None


def person() -> UUID:
    user = current_user.get()
    if user is None:
        raise LookupError("sin persona no hay credencial de nadie")
    return user


READ = text("""
    select key, ciphertext, hint, created_at, last_used_at
    from hub.hub_credential
    where connection_id = :connection and key = :key
""")

STORE = text("""
    insert into hub.hub_credential (connection_id, key, ciphertext, hint)
    values (:connection, :key, :ciphertext, :hint)
    on conflict (user_id, connection_id, key) do update
    set ciphertext = excluded.ciphertext, hint = excluded.hint, created_at = now(),
        last_used_at = null
""")


async def status(
    connection: AsyncConnection, connection_id: UUID, keys: tuple[str, ...]
) -> list[Status]:
    found = []
    for key in keys:
        row = (
            await connection.execute(READ, {"connection": connection_id, "key": key})
        ).one_or_none()
        found.append(
            Status(key=key, configured=False)
            if row is None
            else Status(
                key=key,
                configured=True,
                hint=row.hint,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
            )
        )
    return found


async def store(
    connection: AsyncConnection, provider: str, connection_id: UUID, key: str, secret: str
) -> None:
    sealed = vault(provider).seal(person(), _name(connection_id, key), secret)
    await connection.execute(
        STORE,
        {"connection": connection_id, "key": key, "ciphertext": sealed, "hint": hint(secret)},
    )


async def use(
    connection: AsyncConnection, provider: str, connection_id: UUID, key: str
) -> str | None:
    row = (await connection.execute(READ, {"connection": connection_id, "key": key})).one_or_none()
    if row is None:
        return None
    box = vault(provider)
    try:
        secret = box.open(person(), _name(connection_id, key), row.ciphertext)
    except Undecipherable:
        return None
    if box.stale(row.ciphertext):
        await store(connection, provider, connection_id, key, secret)
    await connection.execute(
        text(
            "update hub.hub_credential set last_used_at = now() "
            "where connection_id = :connection and key = :key"
        ),
        {"connection": connection_id, "key": key},
    )
    return secret
