from collections.abc import Sequence

from alembic import op

revision: str = "0028_events_listed_and_figures"
down_revision: str | None = "0027_indexes_for_keys_and_owners"
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
    consumes text[];
    receives text[];
begin
    if module_id !~ '^[a-z][a-z0-9_]{1,30}$' then
        raise exception 'invalid module id: %', module_id
            using hint = 'lowercase letters, digits and underscore, starting with a letter';
    end if;

    role_name := 'mod_' || module_id;
    reader_name := role_name || '_read';
    login_name := 'svc_' || module_id;

    if not exists (select 1 from pg_catalog.pg_roles where rolname = role_name) then
        -- Sin login: el rol lleva los permisos, no las credenciales (ADR-0013).
        execute format('create role %I nologin', role_name);
    end if;

    -- SET para poder aplicar las tablas como el módulo; INHERIT no, para que el kernel no lea
    -- los datos de un módulo sin ponerse su rol a propósito.
    execute format('grant %I to current_user with set true, inherit false', role_name);

    -- El rol del scope de lectura: lo mismo que ve el módulo, sin poder cambiar nada. Las
    -- tablas se le conceden al aplicarlas, como el dueño (kernel.schemas); aquí, lo que es del
    -- kernel: el schema y la vista de eventos.
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

    -- Lo suyo y lo que declara consumir de Hub, que es lo que el kernel validó al
    -- registrar el manifiesto (ADR-0045). Sale de `kernel.modules` y no de un argumento: la firma
    -- no cambia, y el kernel anterior, que la llama igual, deja la misma vista.
    select coalesce(array_agg(consumed), '{}')
    into consumes
    from kernel.modules m,
         jsonb_array_elements_text(coalesce(m.manifest->'consumes', '[]'::jsonb)) as consumed
    where m.id = module_id;

    -- Y los contratos que recibe (ADR-0081), como lista de tipos fijada aquí (T-V14): los de cada
    -- app cuyo manifiesto dice que ese tipo suyo cumple uno de ellos. El tipo lleva el prefijo de
    -- su app (`vitals.metric`). Con una lista literal la consulta usa el
    -- índice por tipo en vez de cruzar con `kernel.modules` en cada lectura. El precio: cuando
    -- cambia lo que publica una app, se reaprovisiona a quien recibe (`reprovision_receivers`).
    select coalesce(array_agg(distinct published->>'type'), '{}')
    into receives
    from kernel.modules p,
         jsonb_array_elements(coalesce(p.manifest->'publishes', '[]'::jsonb)) as published
    -- Solo los tipos con el id de su app delante: un manifiesto que declarase uno ajeno no
    -- haría pasar por suyo lo de otra app (el registro ya lo rechaza; aquí tampoco entra).
    where split_part(published->>'type', '.', 1) = p.id
      and published->>'contract' in (
        select received
        from kernel.modules m,
             jsonb_array_elements_text(coalesce(m.manifest->'receives', '[]'::jsonb)) as received
        where m.id = module_id
    );

    -- Lo recibido, solo si viene de la app que publica ese tipo: el tipo lleva su id delante
    -- (lo exige el manifiesto), así que es la misma pareja (módulo, tipo) que antes, sin dejar
    -- entrar un evento que otra app mandase con un tipo ajeno.
    execute format(
        'create or replace view %I.events with (security_invoker = false) as '
        'select id, ts, ingested_at, module, source, type, entity_id, payload '
        'from kernel.events where module = %L or type = any(%L::text[]) '
        'or (type = any(%L::text[]) and module = split_part(type, ''.'', 1))',
        module_id, module_id, consumes, receives
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


RECEIVERS_TRIGGER = """
create or replace function kernel.reprovision_receivers()
returns trigger
language plpgsql
set search_path = pg_catalog
as $reprovision$
declare
    changed text;
begin
    changed := case when tg_op = 'DELETE' then old.id else new.id end;
    if tg_op = 'UPDATE'
       and new.manifest->'publishes' is not distinct from old.manifest->'publishes' then
        return null;
    end if;
    perform kernel.provision_module(m.id)
    from kernel.modules m
    where m.id <> changed
      and m.enabled
      and jsonb_array_length(coalesce(m.manifest->'receives', '[]'::jsonb)) > 0
      and exists (select 1 from pg_catalog.pg_namespace n where n.nspname = m.id);
    return null;
end;
$reprovision$
"""
RECEIVERS_ON = """
create trigger modules_publishes_changed
after insert or update of manifest or delete on kernel.modules
for each row execute function kernel.reprovision_receivers()
"""

FIGURES = (
    "create index if not exists events_metric_key_day_idx on kernel.events "
    "(type, (payload->'metric'->>'key'), (payload->'metric'->>'day')) where payload ? 'metric'"
)
RECORDS = (
    "create index if not exists events_record_id_idx on kernel.events "
    "(type, (payload->'record'->>'id')) where payload ? 'record'"
)


def upgrade() -> None:
    op.execute(PROVISION_MODULE)
    op.execute("revoke all on function kernel.provision_module(text) from public")
    op.execute(RECEIVERS_TRIGGER)
    op.execute("drop trigger if exists modules_publishes_changed on kernel.modules")
    op.execute(RECEIVERS_ON)
    op.execute("revoke all on function kernel.reprovision_receivers() from public")
    op.execute(FIGURES)
    op.execute(RECORDS)
    op.execute("select kernel.provision_module(id) from kernel.modules where enabled")


def downgrade() -> None:
    op.execute("drop trigger if exists modules_publishes_changed on kernel.modules")
    op.execute("drop function if exists kernel.reprovision_receivers()")
    op.execute("drop index if exists kernel.events_record_id_idx")
    op.execute("drop index if exists kernel.events_metric_key_day_idx")
