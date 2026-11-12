from __future__ import annotations

import os
import sys
from uuid import UUID

import httpx
from sqlalchemy import text

from arga_contracts import notify
from arga_contracts import records as fichas
from arga_contracts.records import Every
from arga_module.publisher import Publisher
from arga_tenancy import as_user
from notebook import digest, export, mirror
from notebook.db import as_module, engine

MODULE = "notebook"
MIRROR = Every(float(os.environ.get("MIRROR_EVERY_SECONDS", "30")))
MIRROR_FULL = Every(float(os.environ.get("MIRROR_FULL_EVERY_SECONDS", "21600")))
DIGEST = Every(float(os.environ.get("DIGEST_EVERY_SECONDS", "900")))
NOTIFY = Every(float(os.environ.get("NOTIFY_EVERY_SECONDS", "300")))
EXPORT = Every(float(os.environ.get("EXPORT_EVERY_SECONDS", "600")))

LOCK = text("select pg_try_advisory_xact_lock(hashtext('notebook_refresh'), hashtext(:user))")


def _said(what: str, error: Exception) -> None:
    print(f"{what} · {type(error).__name__}: {error}", file=sys.stderr, flush=True)


async def _mirror(full: bool) -> None:
    try:
        async with as_module() as connection:
            done = await mirror.derive(connection, full)
        if any(done.values()):
            print(f"fichas · {done}", flush=True)
    except Exception as error:  # noqa: BLE001 - una persona no tumba las fichas de otra
        _said("fichas", error)


async def _digest() -> None:
    try:
        async with as_module() as connection:
            done = await digest.refresh(connection)
        if done.get("written") or done.get("failed"):
            print(f"digest · {done}", flush=True)
    except Exception as error:  # noqa: BLE001 - una persona no tumba el digest de otra
        _said("digest", error)


async def _export(client: httpx.AsyncClient) -> None:
    try:
        outcome = (await export.push(as_module, client))["outcome"]
        if outcome in ("ok", "error"):
            print(f"export · {outcome}", flush=True)
    except Exception as error:  # noqa: BLE001 - una persona no tumba la copia de las demás
        _said("export", error)


async def _prune() -> None:
    try:
        async with as_module() as connection:
            await fichas.prune(connection, MODULE)
    except Exception as error:  # noqa: BLE001 - podar no para lo que se publica
        _said("poda", error)


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    del fresh
    with as_user(user):
        async with engine().begin() as held:
            if not await held.scalar(LOCK, {"user": str(user)}):
                return
            if MIRROR.due(user):
                await _mirror(MIRROR_FULL.due(user))
            if DIGEST.due(user):
                await _digest()
            await notify.refresh(client, engine, MODULE, digest.notifications, NOTIFY, user)
            if EXPORT.due(user):
                await _export(client)
            await _prune()


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
