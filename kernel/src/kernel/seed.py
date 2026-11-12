from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from kernel.db import engine
from kernel.events import EventIn, ingest
from kernel.preferences import instance_defaults

SOURCE = "seed"
MODULE = "finance"
KIND = "merchant"

SPELLINGS = ["ALBA MARKET 221", "SUPERM. ALBA 0221", "ALBA MARKET SA"]

UNMATCHED_SPELLING = SPELLINGS[1]

LONERS = ["PANADERIA LOS TILOS", "E.S. KM-42 NORTE"]

START = datetime(2026, 9, 1, 9, 30, tzinfo=UTC)

CLEAR_EVENTS = text("delete from kernel.events where source = :source")
OWN_ENTITIES = "select entity_id from kernel.entity_aliases where source = :source"
UNLINK_ENTITIES = text(
    f"update kernel.entities set merged_into = null where id in ({OWN_ENTITIES})"
)
CLEAR_ENTITIES = text(f"delete from kernel.entities where id in ({OWN_ENTITIES})")


def events() -> list[dict]:
    planned = []
    for index, alias in enumerate(SPELLINGS):
        for repeat in range(2):
            planned.append((alias, index * 2 + repeat, -12.40 - index - repeat * 3))
    for index, alias in enumerate(LONERS):
        planned.append((alias, len(SPELLINGS) * 2 + index, -3.20 - index))

    currency = instance_defaults().currency
    return [
        {
            "ts": (START + timedelta(days=offset)).isoformat(),
            "module": MODULE,
            "source": SOURCE,
            "type": "finance.transaction",
            "entity": {"alias": alias, "kind": KIND},
            "payload": {"amount": round(amount, 2), "currency": currency, "raw_description": alias},
            "dedup_hash": f"{SOURCE}:tx:{offset:03d}",
        }
        for alias, offset, amount in planned
    ]


async def load() -> tuple[int, int]:
    planned = events()
    created = 0
    for event in planned:
        result = await ingest(EventIn.model_validate(event))
        created += int(result.created)
    return len(planned), created


async def clear() -> None:
    async with engine().begin() as connection:
        await connection.execute(CLEAR_EVENTS, {"source": SOURCE})
        await connection.execute(UNLINK_ENTITIES, {"source": SOURCE})
        await connection.execute(CLEAR_ENTITIES, {"source": SOURCE})


async def pending() -> int:
    async with engine().connect() as connection:
        return await connection.scalar(
            text("select count(*) from kernel.resolution_queue where resolved_at is null")
        )


async def _run(wipe: bool) -> str:
    try:
        if wipe:
            await clear()
            return f"seed borrado · cola pendiente: {await pending()}"
        sent, created = await load()
        return (
            f"seed cargado · {sent} eventos, {created} nuevos · cola pendiente: {await pending()}"
        )
    finally:
        await engine().dispose()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in ([], ["--clear"]):
        print("uso: python -m kernel.seed [--clear]", file=sys.stderr)
        return 2

    try:
        print(asyncio.run(_run(wipe=arguments == ["--clear"])))
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"seed fallido: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
