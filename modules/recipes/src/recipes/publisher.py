from __future__ import annotations

import sys
from uuid import UUID

import httpx

from arga_contracts import records as fichas
from arga_module.db import engine
from arga_module.publisher import Publisher
from arga_tenancy import as_user, users
from recipes import hub, pantry, records

MODULE = "recipes"

RECORDS = fichas.Every()
HANDED = {"done": False}


async def hand_over_usda(client: httpx.AsyncClient) -> bool:
    if not hub.usda_key():
        return True
    try:
        people = await users(client)
    except httpx.HTTPError:
        return False
    if len(people) != 1:
        return True
    with as_user(people[0]):
        done = await hub.hand_over_usda(client)
    if done:
        print("publisher · the USDA key is now the only person's credential", flush=True)
    return done


async def refresh(client: httpx.AsyncClient, user: UUID, fresh: bool) -> None:
    if not HANDED["done"]:
        HANDED["done"] = await hand_over_usda(client)
    if fresh:
        RECORDS.forget(user)
    await fichas.refresh(client, engine, MODULE, records.build, RECORDS, user)
    try:
        async with PUBLISHER.as_module() as connection:
            if filled := await pantry.refill(connection, client):
                print(f"publisher · micros for {filled} food(s)", flush=True)
    except pantry.Unavailable as error:
        print(f"publisher · micros: {error}", file=sys.stderr, flush=True)
    except Exception as error:  # noqa: BLE001 - micros do not stop what is published
        print(f"publisher · micros: {type(error).__name__}: {error}", file=sys.stderr, flush=True)


PUBLISHER = Publisher(MODULE, engine, refresh)
publish_pending = PUBLISHER.publish_pending
run_once = PUBLISHER.run_once


def main() -> int:
    return PUBLISHER.main()


if __name__ == "__main__":
    raise SystemExit(main())
