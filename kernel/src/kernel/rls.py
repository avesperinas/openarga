from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_SPACES_SQL as SPACES
from arga_tenancy import CURRENT_USER_SQL as CURRENT
from kernel.provision import role_for

POLICY = "arga_owner"

OWN = f"user_id = (select {CURRENT})"
IN_SPACE = f"(space_id is null and {OWN}) or space_id = any((select {SPACES})::uuid[])"
SEEN_IN_SPACE = f"{OWN} or space_id = any((select {SPACES})::uuid[])"

CATALOG_IN_SPACE = "arga:catalog+space"

VISIBLE = {
    "arga:person": OWN,
    "arga:catalog": f"user_id is null or {OWN}",
    CATALOG_IN_SPACE: f"user_id is null or {SEEN_IN_SPACE}",
    "arga:shared": SEEN_IN_SPACE,
}
WRITABLE = {
    "arga:person": OWN,
    "arga:catalog": OWN,
    CATALOG_IN_SPACE: IN_SPACE,
    "arga:shared": IN_SPACE,
}
CLASSES = ["arga:person", "arga:catalog", "arga:shared"]

TABLES = text("""
    select format('%I.%I', n.nspname, c.relname) as name,
           obj_description(c.oid, 'pg_class') as class_,
           c.relrowsecurity as enabled,
           c.relforcerowsecurity as forced,
           exists (select 1 from pg_catalog.pg_policy p
                   where p.polrelid = c.oid and p.polname = :policy) as has_policy,
           (select obj_description(p.oid, 'pg_policy') from pg_catalog.pg_policy p
            where p.polrelid = c.oid and p.polname = :policy) as signed,
           exists (select 1 from pg_catalog.pg_attribute a
                   where a.attrelid = c.oid and a.attname = 'space_id' and not a.attisdropped)
             as has_space
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'r'
      and n.nspname = :schema
      and obj_description(c.oid, 'pg_class') = any(:classes)
    order by c.relname
""")


def rule_of(table_class: str, has_space: bool) -> str:
    if table_class == "arga:catalog" and has_space:
        return CATALOG_IN_SPACE
    return table_class


def signature(table_class: str) -> str:
    rule = f"{VISIBLE[table_class]}\n{WRITABLE[table_class]}"
    return f"arga:{hashlib.sha256(rule.encode()).hexdigest()[:16]}"


def statements(
    name: str,
    table_class: str,
    enabled: bool,
    forced: bool,
    has_policy: bool,
    signed: str | None = None,
) -> list[str]:
    pending = []
    if not enabled:
        pending.append(f"alter table {name} enable row level security")
    if not forced:
        pending.append(f"alter table {name} force row level security")
    rule = f"using ({VISIBLE[table_class]}) with check ({WRITABLE[table_class]})"
    expected = signature(table_class)
    if not has_policy:
        pending.append(f"create policy {POLICY} on {name} {rule}")
    elif signed != expected:
        pending.append(f"alter policy {POLICY} on {name} {rule}")
    if signed != expected:
        pending.append(f"comment on policy {POLICY} on {name} is '{expected}'")
    return pending


async def enforce(connection: AsyncConnection, schema: str, as_module: bool = True) -> list[str]:
    rows = (
        await connection.execute(TABLES, {"schema": schema, "policy": POLICY, "classes": CLASSES})
    ).all()
    touched = []
    if as_module and rows:
        await connection.execute(text(f'set local role "{role_for(schema)}"'))
    for row in rows:
        pending = statements(
            row.name,
            rule_of(row.class_, row.has_space),
            row.enabled,
            row.forced,
            row.has_policy,
            row.signed,
        )
        for statement in pending:
            await connection.execute(text(statement))
        if pending:
            touched.append(row.name)
    if as_module and rows:
        await connection.execute(text("reset role"))
    return touched
