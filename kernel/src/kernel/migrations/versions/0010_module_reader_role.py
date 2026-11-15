from collections.abc import Sequence

from alembic import op

revision: str = "0010_module_reader_role"
down_revision: str | None = "0009_provision_without_superuser"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROVISION_MODULE = """
create or replace function kernel.provision_module(module_id text)
returns void
language plpgsql
set search_path = pg_catalog
as $provision$
declare
    role_name text;
    reader_name text;
    login_name text;
    foreign_object regclass;
begin
    if module_id !~ '^[a-z][a-z0-9_]{1,30}$' then
        raise exception 'invalid module id: %', module_id
            using hint = 'lowercase letters, digits and underscore, starting with a letter';
    end if;

    role_name := 'mod_' || module_id;
    reader_name := role_name || '_read';
    login_name := 'svc_' || module_id;

    if not exists (select 1 from pg_catalog.pg_roles where rolname = role_name) then
        -- No login: the role carries the permissions, not the credentials (ADR-0013).
        execute format('create role %I nologin', role_name);
    end if;

    -- SET so the tables can be applied as the module; not INHERIT, so the kernel does not
    -- read a module's data without taking its role on purpose.
    execute format('grant %I to current_user with set true, inherit false', role_name);

    -- The read scope's role: what the module sees, without changing anything. Tables are
    -- granted to it when applied, like the owner (kernel.schemas); here, what belongs to the
    -- kernel: the schema and the events view.
    if not exists (select 1 from pg_catalog.pg_roles where rolname = reader_name) then
        execute format('create role %I nologin', reader_name);
    end if;
    execute format('grant %I to current_user with set true, inherit false', reader_name);

    execute format('create schema if not exists %I', module_id);

    execute format('grant usage, create on schema %I to %I', module_id, role_name);
    execute format('grant usage on schema %I to %I', module_id, reader_name);

    for foreign_object in
        select c.oid::regclass
        from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname = module_id
          and c.relkind in ('r', 'p', 'm', 'f', 'S')
          and c.relowner <> (select oid from pg_catalog.pg_roles where rolname = role_name)
    loop
        execute format('grant all on %s to %I', foreign_object, role_name);
    end loop;

    execute format(
        'alter default privileges in schema %I grant all on tables to %I', module_id, role_name
    );
    execute format(
        'alter default privileges in schema %I grant all on sequences to %I', module_id, role_name
    );

    execute format('revoke all on schema kernel from %I', role_name);
    execute format('revoke all on all tables in schema kernel from %I', role_name);
    execute format('revoke all on schema kernel from %I', reader_name);
    execute format('revoke all on all tables in schema kernel from %I', reader_name);

    execute format(
        'create or replace view %I.events with (security_invoker = false) as '
        'select id, ts, ingested_at, module, source, type, entity_id, payload '
        'from kernel.events where module = %L',
        module_id, module_id
    );
    execute format('revoke all on %I.events from %I', module_id, role_name);
    execute format('grant select on %I.events to %I', module_id, role_name);
    execute format('revoke all on %I.events from %I', module_id, reader_name);
    execute format('grant select on %I.events to %I', module_id, reader_name);

    if exists (select 1 from pg_catalog.pg_roles where rolname = login_name) then
        execute format('grant %I to %I', role_name, login_name);
        execute format('grant %I to %I', reader_name, login_name);
    end if;
end;
$provision$
"""


def upgrade() -> None:
    op.execute(PROVISION_MODULE)
    op.execute("revoke all on function kernel.provision_module(text) from public")


def downgrade() -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    path = Path(__file__).with_name("0009_provision_without_superuser.py")
    spec = spec_from_file_location("provision_0009", path)
    previous = module_from_spec(spec)
    spec.loader.exec_module(previous)
    op.execute(previous.PROVISION_MODULE)
