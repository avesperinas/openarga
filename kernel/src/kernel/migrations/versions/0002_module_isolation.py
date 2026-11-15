from collections.abc import Sequence

from alembic import op

revision: str = "0002_module_isolation"
down_revision: str | None = "0001_core"
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
begin
    if module_id !~ '^[a-z][a-z0-9_]{1,30}$' then
        raise exception 'invalid module id: %', module_id
            using hint = 'lowercase letters, digits and underscore, starting with a letter';
    end if;

    role_name := 'mod_' || module_id;

    if not exists (select 1 from pg_catalog.pg_roles where rolname = role_name) then
        -- No login: the role carries the permissions, not the credentials. The user the
        -- service connects with is created by infra and inherits from this one.
        execute format('create role %I nologin', role_name);
    end if;

    execute format('create schema if not exists %I', module_id);

    execute format('grant usage, create on schema %I to %I', module_id, role_name);
    execute format('grant all on all tables in schema %I to %I', module_id, role_name);
    execute format('grant all on all sequences in schema %I to %I', module_id, role_name);
    execute format(
        'alter default privileges in schema %I grant all on tables to %I', module_id, role_name
    );
    execute format(
        'alter default privileges in schema %I grant all on sequences to %I', module_id, role_name
    );

    -- Nothing on kernel.*. Revoking what was never granted is a no-op: it is there so that
    -- reprovisioning undoes a grant made by hand in a psql session.
    execute format('revoke all on schema kernel from %I', role_name);
    execute format('revoke all on all tables in schema kernel from %I', role_name);

    -- The only read of events, filtered by module. security_invoker = false: the view
    -- queries with its owner's permissions, so the role reads its events without a single
    -- GRANT on kernel.events. dedup_hash stays out: it is the connector's idempotency, not
    -- part of the event.
    execute format(
        'create or replace view %I.events with (security_invoker = false) as '
        'select id, ts, ingested_at, module, source, type, entity_id, payload '
        'from kernel.events where module = %L',
        module_id, module_id
    );
    -- The revoke is needed: `alter default privileges ... on tables` also covers views,
    -- so without it the view is born with ALL and the module writes to kernel.events
    -- through it. A test caught it before production.
    execute format('revoke all on %I.events from %I', module_id, role_name);
    execute format('grant select on %I.events to %I', module_id, role_name);
end;
$provision$
"""


def upgrade() -> None:
    op.execute(PROVISION_MODULE)
    op.execute("revoke all on function kernel.provision_module(text) from public")


def downgrade() -> None:
    op.execute("drop function if exists kernel.provision_module(text)")
