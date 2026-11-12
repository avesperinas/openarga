from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from kernel.provision import role_for

PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")

EXISTENCE = text("""
    select
        exists (
            select 1 from pg_catalog.pg_namespace where nspname = cast(:schema as name)
        ) as has_schema,
        exists (
            select 1 from pg_catalog.pg_roles where rolname = cast(:role as name)
        ) as has_role
""")

OWN_SCHEMA = text("""
    select
        has_schema_privilege(cast(:role as name), cast(:schema as text), 'USAGE') as may_use,
        has_schema_privilege(cast(:role as name), cast(:schema as text), 'CREATE') as may_create
""")

EVENTS_VIEW = text(r"""
    select regexp_replace(pg_catalog.pg_get_viewdef(c.oid, true), '\s+', ' ', 'g') as definition
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = cast(:schema as name)
      and c.relname = 'events'
      and c.relkind = 'v'
""")

ACCESS = text("""
    select
        cast(n.nspname as text) as schema_name,
        cast(c.relname as text) as object_name,
        has_schema_privilege(cast(:role as name), cast(n.nspname as text), 'USAGE')
            as schema_usage,
        has_table_privilege(cast(:role as name), c.oid, 'SELECT') as may_select,
        has_table_privilege(cast(:role as name), c.oid, 'INSERT') as may_insert,
        has_table_privilege(cast(:role as name), c.oid, 'UPDATE') as may_update,
        has_table_privilege(cast(:role as name), c.oid, 'DELETE') as may_delete
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'p', 'v', 'm')
      and (
        n.nspname = 'kernel'
        or exists (
            select 1 from pg_catalog.pg_roles r where r.rolname = 'mod_' || n.nspname
        )
      )
    order by n.nspname, c.relname
""")


class ModuleNotProvisioned(Exception):
    def __init__(self, module_id: str, missing: list[str]) -> None:
        self.module_id = module_id
        self.missing = missing
        super().__init__(f"module '{module_id}' is not provisioned: missing {', '.join(missing)}")


class SchemaAccess(BaseModel):
    usage: bool
    create: bool


class ObjectAccess(BaseModel):
    object: str
    granted: list[str]
    usable: bool


class EventsView(BaseModel):
    name: str
    definition: str


class Isolation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    module: str
    db_schema: str = Field(alias="schema")
    role: str
    own_schema: SchemaAccess
    events: EventsView | None
    access: list[ObjectAccess]


async def describe(connection: AsyncConnection, module_id: str) -> Isolation:
    role = role_for(module_id)
    parameters = {"schema": module_id, "role": role}

    existence = (await connection.execute(EXISTENCE, parameters)).one()
    present = (
        (f"schema {module_id}", existence.has_schema),
        (f"role {role}", existence.has_role),
    )
    missing = [name for name, exists in present if not exists]
    if missing:
        raise ModuleNotProvisioned(module_id, missing)

    own = (await connection.execute(OWN_SCHEMA, parameters)).one()
    definition = (await connection.execute(EVENTS_VIEW, parameters)).scalar()
    rows = (await connection.execute(ACCESS, parameters)).all()

    access = []
    for row in rows:
        granted = [
            privilege
            for privilege, allowed in zip(
                PRIVILEGES,
                (row.may_select, row.may_insert, row.may_update, row.may_delete),
                strict=True,
            )
            if allowed
        ]
        access.append(
            ObjectAccess(
                object=f"{row.schema_name}.{row.object_name}",
                granted=granted,
                usable=bool(granted) and row.schema_usage,
            )
        )

    return Isolation(
        module=module_id,
        schema=module_id,
        role=role,
        own_schema=SchemaAccess(usage=own.may_use, create=own.may_create),
        events=EventsView(name=f"{module_id}.events", definition=definition)
        if definition
        else None,
        access=access,
    )
