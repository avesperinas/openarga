from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from kernel.db import engine

MODULE_ID_PATTERN = r"^[a-z][a-z0-9_]{1,30}$"

ROLE_PREFIX = "mod_"


def role_for(module_id: str) -> str:
    return f"{ROLE_PREFIX}{module_id}"


def reader_for(module_id: str) -> str:
    return f"{role_for(module_id)}_read"


async def provision(module_id: str) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text("select kernel.provision_module(:module_id)"), {"module_id": module_id}
        )


async def _run(module_id: str) -> None:
    try:
        await provision(module_id)
    finally:
        await engine().dispose()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("uso: python -m kernel.provision <module_id>", file=sys.stderr)
        return 2
    try:
        asyncio.run(_run(arguments[0]))
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"aprovisionamiento fallido: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
