from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.provision import role_for

OWNED = ("arga:person",)

TABLES = text("""
    select format('%I.%I', n.nspname, c.relname) as name
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    join pg_catalog.pg_attribute a on a.attrelid = c.oid and a.attname = 'user_id'
    where c.relkind = 'r'
      and n.nspname = :schema
      and obj_description(c.oid, 'pg_class') = any(:classes)
      and not a.attnotnull
    order by c.relname
""")


class AmbiguousOwner(RuntimeError):
    pass


async def sole_owner(connection: AsyncConnection) -> tuple[int, UUID | None]:
    rows = (await connection.execute(text("select id from kernel.users limit 2"))).all()
    return len(rows), rows[0].id if len(rows) == 1 else None


async def backfill_module(connection: AsyncConnection, module_id: str) -> dict[str, int]:
    exists = await connection.scalar(
        text("select 1 from pg_catalog.pg_namespace where nspname = :schema"), {"schema": module_id}
    )
    if not exists:
        return {}
    tables = (
        (await connection.execute(TABLES, {"schema": module_id, "classes": list(OWNED)}))
        .scalars()
        .all()
    )
    if not tables:
        return {}

    count, owner = await sole_owner(connection)
    role = role_for(module_id)
    await connection.execute(text(f'set local role "{role}"'))
    moved: dict[str, int] = {}
    for table in tables:
        if owner is not None:
            forced = await connection.scalar(
                text(
                    "select relforcerowsecurity from pg_catalog.pg_class "
                    "where oid = cast(:t as regclass)"
                ),
                {"t": table},
            )
            if forced:
                await connection.execute(text(f"alter table {table} no force row level security"))

            orphan = await connection.scalar(
                text(f"select 1 from {table} where user_id is null limit 1")
            )
            if not orphan:
                if forced:
                    await connection.execute(text(f"alter table {table} force row level security"))
                continue
            await connection.execute(text(f"alter table {table} disable trigger user"))
            result = await connection.execute(
                text(f"update {table} set user_id = :owner where user_id is null"),
                {"owner": owner},
            )
            await connection.execute(text(f"alter table {table} enable trigger user"))
            if forced:
                await connection.execute(text(f"alter table {table} force row level security"))
            moved[table] = result.rowcount
        elif count > 1:
            forced = await connection.scalar(
                text(
                    "select relforcerowsecurity from pg_catalog.pg_class "
                    "where oid = cast(:t as regclass)"
                ),
                {"t": table},
            )
            if forced:
                await connection.execute(text(f"alter table {table} no force row level security"))
            orphan = await connection.scalar(
                text(f"select 1 from {table} where user_id is null limit 1")
            )
            if forced:
                await connection.execute(text(f"alter table {table} force row level security"))
            if orphan:
                await connection.execute(text("reset role"))
                raise AmbiguousOwner(
                    f"{table} tiene filas sin dueño y hay varias personas: no se puede saber de "
                    "quién son. Hay que dárselas a mano antes de arrancar (ADR-0028)."
                )
    await connection.execute(text("reset role"))
    return moved
