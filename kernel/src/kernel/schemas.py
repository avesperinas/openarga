from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.provision import reader_for, role_for
from kernel.sealed import seal

SCHEMA_DIR = "schema"


@dataclass(frozen=True)
class SchemaFile:
    name: str
    sql: str


def schema_files(root: Path, module_id: str) -> list[Path]:
    directory = root / module_id / SCHEMA_DIR
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.sql") if path.is_file())


def from_disk(root: Path, module_id: str) -> list[SchemaFile]:
    return [
        SchemaFile(path.name, path.read_text(encoding="utf-8"))
        for path in schema_files(root, module_id)
    ]


def has_statements(sql: str) -> bool:
    body = "\n".join(
        line for line in sql.splitlines() if line.strip() and not line.strip().startswith("--")
    )
    return bool(body.strip())


async def _execute_script(connection: AsyncConnection, sql: str) -> None:
    raw = await connection.get_raw_connection()
    await raw.driver_connection.execute(sql)


class ChangedMigration(RuntimeError):
    pass


APPLIED = text("""
    select filename, sha256 from kernel.module_migrations where module = :module
""")

RECORD = text("""
    insert into kernel.module_migrations (module, filename, sha256)
    values (:module, :filename, :sha256)
""")


FORCED_CATALOGS = text("""
    select format('%I.%I', n.nspname, c.relname) as name
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = :schema and c.relkind = 'r' and c.relforcerowsecurity
      and obj_description(c.oid, 'pg_class') = 'arga:catalog'
""")


async def _unforce_catalogs(connection: AsyncConnection, module_id: str, role: str) -> None:
    tables = (await connection.execute(FORCED_CATALOGS, {"schema": module_id})).scalars().all()
    if not tables:
        return
    await connection.execute(text(f'set local role "{role}"'))
    for table in tables:
        await connection.execute(text(f"alter table {table} no force row level security"))
    await connection.execute(text("reset role"))


async def apply(
    connection: AsyncConnection, files: Sequence[SchemaFile], module_id: str
) -> list[str]:
    done = {
        row.filename: row.sha256
        for row in (await connection.execute(APPLIED, {"module": module_id})).all()
    }
    applied: list[str] = []
    role = role_for(module_id)

    for file in sorted(files, key=lambda file: file.name):
        sql = file.sql
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()

        if file.name in done:
            if done[file.name] != digest:
                raise ChangedMigration(
                    f"{module_id}/schema/{file.name} ya se aplicó y su contenido ha cambiado. "
                    "Un fichero aplicado no se edita: el cambio va en uno nuevo."
                )
            continue

        if has_statements(sql):
            await _unforce_catalogs(connection, module_id, role)
            await connection.execute(text(f'set local role "{role}"'))
            await _execute_script(connection, sql)
            await connection.execute(text("reset role"))
            applied.append(file.name)

        await connection.execute(
            RECORD, {"module": module_id, "filename": file.name, "sha256": digest}
        )

    await grant_to_reader(connection, module_id)
    await connection.execute(text("reset role"))
    await seal(connection, module_id)
    await connection.execute(text("reset role"))
    return applied


OWN_TABLES = text("""
    select format('%I.%I', t.schemaname, t.tablename)
    from pg_catalog.pg_tables t
    where t.schemaname = :schema and t.tableowner = :role
      and not exists (
          select 1
          from pg_catalog.pg_class c
          join pg_catalog.pg_namespace n on n.oid = c.relnamespace
          join pg_catalog.pg_attribute a on a.attrelid = c.oid and a.attname = 'ciphertext'
           and not a.attisdropped and a.atttypid = 'bytea'::regtype
          where n.nspname = t.schemaname and c.relname = t.tablename
      )
    order by t.tablename
""")


async def grant_to_reader(connection: AsyncConnection, module_id: str) -> None:
    role = role_for(module_id)
    reader = reader_for(module_id)
    exists = await connection.scalar(
        text("select 1 from pg_catalog.pg_roles where rolname = :reader"), {"reader": reader}
    )
    if not exists:
        return
    await connection.execute(text(f'set local role "{role}"'))
    tables = (await connection.execute(OWN_TABLES, {"schema": module_id, "role": role})).scalars()
    for table in tables:
        await connection.execute(text(f'grant select on {table} to "{reader}"'))
