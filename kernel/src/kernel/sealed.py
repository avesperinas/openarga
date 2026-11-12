from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from kernel.provision import reader_for, role_for

SECRET_TABLES = text("""
    select format('%I.%I', n.nspname, c.relname) as name
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    join pg_catalog.pg_attribute a on a.attrelid = c.oid and a.attname = 'ciphertext'
     and not a.attisdropped and a.atttypid = 'bytea'::regtype
    where c.relkind = 'r' and n.nspname = :schema
    order by 1
""")

OTHER_GRANTEES = text("""
    with acls as (
        select acl.grantee
        from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        cross join lateral aclexplode(c.relacl) acl
        where n.nspname = :schema and c.relname = :table
        union
        select acl.grantee
        from pg_catalog.pg_attribute a
        join pg_catalog.pg_class c on c.oid = a.attrelid
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        cross join lateral aclexplode(a.attacl) acl
        where n.nspname = :schema and c.relname = :table
    )
    select distinct case when grantee = 0 then 'PUBLIC' else pg_get_userbyid(grantee) end as grantee
    from acls
    where grantee = 0 or pg_get_userbyid(grantee) <> :owner
""")


async def secret_tables(connection: AsyncConnection, schema: str) -> list[str]:
    return list((await connection.execute(SECRET_TABLES, {"schema": schema})).scalars())


OPEN_COLUMNS = text("""
    select string_agg(format('%I', a.attname), ', ' order by a.attnum)
    from pg_catalog.pg_attribute a
    join pg_catalog.pg_class c on c.oid = a.attrelid
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = :schema and c.relname = :table
      and a.attnum > 0 and not a.attisdropped and a.attname <> 'ciphertext'
""")


async def seal(connection: AsyncConnection, module_id: str) -> list[str]:
    owner = role_for(module_id)
    reader = reader_for(module_id)
    tables = await secret_tables(connection, module_id)
    if not tables:
        return []
    has_reader = await connection.scalar(
        text("select 1 from pg_catalog.pg_roles where rolname = :reader"), {"reader": reader}
    )
    await connection.execute(text(f'set local role "{owner}"'))
    for name in tables:
        table = name.split(".", 1)[1].strip('"')
        grantees = (
            await connection.execute(
                OTHER_GRANTEES, {"schema": module_id, "table": table, "owner": owner}
            )
        ).scalars()
        for grantee in grantees:
            who = "public" if grantee == "PUBLIC" else f'"{grantee}"'
            await connection.execute(text(f"revoke all on {name} from {who}"))
        if has_reader:
            columns = await connection.scalar(OPEN_COLUMNS, {"schema": module_id, "table": table})
            await connection.execute(text(f'grant select ({columns}) on {name} to "{reader}"'))
    await connection.execute(text("reset role"))
    return tables


REGISTERED = text("""
    select m.id from kernel.modules m
    join pg_catalog.pg_namespace n on n.nspname = m.id
    order by m.id
""")


async def seal_everything(database_url: str) -> dict[str, list[str]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            modules = list((await connection.execute(REGISTERED)).scalars())
            return {module: await seal(connection, module) for module in modules}
    finally:
        await engine.dispose()


def main(database_url: str) -> int:
    try:
        sealed = asyncio.run(seal_everything(database_url))
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"no se pudieron sellar las tablas de secretos: {error}", file=sys.stderr)
        return 1
    for module, tables in sealed.items():
        if tables:
            print(f"sellado    {module}: {', '.join(tables)} solo para mod_{module}")
    return 0
