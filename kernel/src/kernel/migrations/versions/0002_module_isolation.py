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
        -- Sin login: el rol lleva los permisos, no las credenciales. El usuario con el
        -- que se conecta el servicio lo crea infra y hereda de este.
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

    -- Nada sobre kernel.*. Revocar lo que nunca se concedió es un no-op: está para que
    -- reaprovisionar deshaga un grant hecho a mano en una sesión de psql.
    execute format('revoke all on schema kernel from %I', role_name);
    execute format('revoke all on all tables in schema kernel from %I', role_name);

    -- La única lectura de eventos, filtrada por módulo. security_invoker = false: la vista
    -- consulta con los permisos de su dueño, así que el rol lee sus eventos sin recibir un
    -- solo GRANT sobre kernel.events. dedup_hash se queda fuera: es la idempotencia del
    -- conector, no parte del evento.
    execute format(
        'create or replace view %I.events with (security_invoker = false) as '
        'select id, ts, ingested_at, module, source, type, entity_id, payload '
        'from kernel.events where module = %L',
        module_id, module_id
    );
    -- El revoke no sobra: `alter default privileges ... on tables` cubre también las
    -- vistas, así que sin esto la vista nace con ALL y el módulo escribe en kernel.events
    -- a través de ella. Lo cazó un test antes de llegar a producción.
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
