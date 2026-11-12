from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.manifests import Manifest, load_all
from kernel.modules import sync

MODULES = Path(__file__).resolve().parents[4] / "modules"

SHAPE = text("""
    select md5(concat_ws('|',
        (select string_agg(concat_ws(':', c.relname, c.relkind, pg_get_userbyid(c.relowner),
                                     c.relacl::text, c.relrowsecurity, c.relforcerowsecurity),
                           ',' order by c.relname)
         from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = :schema),
        (select string_agg(c.relname || '.' || a.attname || ':'
                           || format_type(a.atttypid, a.atttypmod), ','
                           order by c.relname, a.attnum)
         from pg_class c join pg_namespace n on n.oid = c.relnamespace
         join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
         where n.nspname = :schema),
        (select string_agg(concat_ws(':', p.tablename, p.policyname, p.cmd, p.roles::text,
                                     p.qual, p.with_check), ','
                           order by p.tablename, p.policyname)
         from pg_policies p where p.schemaname = :schema),
        (select count(*) from kernel.module_migrations where module = :schema)
    ))
""")

TABLES = text("""
    select c.relname as name,
           array_agg(a.attname::text order by a.attnum) filter (where a.attgenerated = '')
             as columns
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
    where n.nspname = :schema and c.relkind in ('r', 'p') and not c.relispartition
    group by c.relname
    order by c.relname
""")

SEQUENCES = text("""
    select sequencename as name, last_value, start_value
    from pg_sequences
    where schemaname = :schema
""")


@dataclass
class Applied:
    tables: list[str]
    rows: dict[str, tuple[list[str], bytes]]
    sequences: list[tuple[str, int | None, int]]
    shape: str = ""


_applied: dict[str, Applied] = {}


@cache
def manifests(root: Path = MODULES) -> tuple[Manifest, ...]:
    return tuple(load_all(root))


def quoted(schema: str, table: str) -> str:
    return f'"{schema}"."{table}"'


async def shape(connection: AsyncConnection, schema: str) -> str:
    return (await connection.execute(SHAPE, {"schema": schema})).scalar_one()


async def apply(connection: AsyncConnection, manifest: Manifest, root: Path) -> Applied:
    schema = manifest.id
    await connection.execute(text(f'drop schema if exists "{schema}" cascade'))
    await connection.execute(
        text("delete from kernel.module_migrations where module = :m"), {"m": schema}
    )
    await sync(connection, [manifest], root)
    raw = (await connection.get_raw_connection()).driver_connection
    tables, rows = [], {}
    for table in (await connection.execute(TABLES, {"schema": schema})).all():
        tables.append(table.name)
        if await raw.fetchval(f"select exists (select from {quoted(schema, table.name)})"):
            copied = io.BytesIO()
            await raw.copy_from_table(
                table.name,
                schema_name=schema,
                columns=list(table.columns),
                output=copied,
                format="binary",
            )
            rows[table.name] = (list(table.columns), copied.getvalue())
    sequences = [
        (row.name, row.last_value, row.start_value)
        for row in (await connection.execute(SEQUENCES, {"schema": schema})).all()
    ]
    return Applied(tables, rows, sequences)


async def reset(connection: AsyncConnection, schema: str, applied: Applied) -> None:
    raw = (await connection.get_raw_connection()).driver_connection
    await connection.execute(text("set local session_replication_role = replica"))
    if applied.tables:
        await raw.execute(
            "; ".join(f"delete from {quoted(schema, table)}" for table in applied.tables)
        )
    for table, (columns, copied) in applied.rows.items():
        await raw.copy_to_table(
            table,
            schema_name=schema,
            columns=columns,
            source=io.BytesIO(copied),
            format="binary",
        )
    for name, last_value, start_value in applied.sequences:
        await connection.execute(
            text("select setval(cast(:sequence as regclass), :value, :called)"),
            {
                "sequence": quoted(schema, name),
                "value": start_value if last_value is None else last_value,
                "called": last_value is not None,
            },
        )
    await connection.execute(text("set local session_replication_role = origin"))


async def fresh_modules(
    connection: AsyncConnection,
    *ids: str,
    fresh: Iterable[str] | None = None,
    root: Path = MODULES,
) -> None:
    wanted = [m for m in manifests(root) if m.id in ids]
    chosen = None if fresh is None else set(fresh)
    renewed = [m.id for m in wanted if chosen is None or m.id in chosen]
    for manifest in wanted:
        if manifest.id not in renewed:
            continue
        applied = _applied.get(manifest.id)
        if applied is not None and applied.shape == await shape(connection, manifest.id):
            await reset(connection, manifest.id, applied)
        else:
            _applied[manifest.id] = await apply(connection, manifest, root)
    await sync(connection, wanted, root)
    for schema in renewed:
        _applied[schema].shape = await shape(connection, schema)
