from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from kernel import sealed
from kernel.db import database_url

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    return config


def known_revisions() -> set[str]:
    script = ScriptDirectory.from_config(alembic_config())
    return {revision.revision for revision in script.walk_revisions()}


async def stamped_revision() -> str | None:
    engine = create_async_engine(database_url())
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync: MigrationContext.configure(sync).get_current_revision()
            )
    finally:
        await engine.dispose()


def upgrade(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


def main() -> int:
    try:
        stamped = asyncio.run(stamped_revision())
    except Exception as error:  # noqa: BLE001 - sin base de datos no hay nada que decidir
        print(
            f"no se pudo leer la revisión aplicada: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    if stamped is not None and stamped not in known_revisions():
        print(
            f"la base de datos está en '{stamped}', que esta versión no conoce: es un "
            f"rollback. No se migra y se arranca igual, porque el esquema nuevo tiene que "
            f"servir al código anterior (principio 11).",
            file=sys.stderr,
        )
        return sealed.main(database_url())

    try:
        upgrade()
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"migración fallida: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return sealed.main(database_url())


if __name__ == "__main__":
    raise SystemExit(main())
