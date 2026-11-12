create table macros.macros_entry (
    id          uuid        primary key default gen_random_uuid(),
    eaten_at    timestamptz not null,
    tz          text        not null default 'Europe/Madrid',
    day         date        not null,
    said        text        check (said is null or length(said) <= 1000),
    origin      text        not null check (origin in ('claude', 'app')),
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table macros.macros_entry is 'arga:person';

create index macros_entry_by_day on macros.macros_entry (user_id, day, eaten_at);

create table macros.macros_item (
    id                 uuid    primary key default gen_random_uuid(),
    entry_id           uuid    not null references macros.macros_entry (id) on delete cascade,
    position           smallint not null check (position > 0),
    kind               text    not null check (kind in ('food', 'recipe', 'quick', 'water')),
    food_id            uuid,
    recipe_id          uuid,
    recipe_version_id  uuid,
    name               text    not null check (length(btrim(name)) > 0 and length(name) <= 200),
    quantity           numeric(9, 2) not null check (quantity > 0),
    unit               text    not null check (unit in ('g', 'ml', 'unit', 'serving', 'kcal')),
    grams              numeric(9, 2) check (grams is null or grams >= 0),
    estimated          boolean not null default false,
    basis              jsonb   check (basis is null or jsonb_typeof(basis) = 'object'),
    basis_per          text    check (basis_per in ('100g', 'serving')),
    nutrients          jsonb   not null check (jsonb_typeof(nutrients) = 'object'),
    user_id            uuid    not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (entry_id, position),
    constraint macros_item_reference check (
        (kind = 'food' and food_id is not null and basis is not null)
        or (kind = 'recipe' and recipe_id is not null and recipe_version_id is not null
            and basis is not null)
        or (kind = 'quick' and unit = 'kcal')
        or (kind = 'water' and unit = 'ml')
    )
);
comment on table macros.macros_item is 'arga:person';

create index macros_item_by_entry on macros.macros_item (entry_id, position);

create table macros.macros_target (
    id          uuid    primary key default gen_random_uuid(),
    valid_from  date    not null,
    kcal        numeric(6, 0) check (kcal is null or kcal between 500 and 10000),
    protein     numeric(5, 1) check (protein is null or protein between 0 and 1000),
    carbs       numeric(5, 1) check (carbs is null or carbs between 0 and 1000),
    fat         numeric(5, 1) check (fat is null or fat between 0 and 1000),
    created_at  timestamptz not null default now(),
    user_id     uuid    not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, valid_from)
);
comment on table macros.macros_target is 'arga:person';

create table macros.macros_reference (
    nutrient  text    not null check (nutrient ~ '^[a-z][a-z0-9_]*$'),
    kind      text    not null check (kind in ('min', 'max', 'energy_share')),
    value     numeric(10, 3) not null check (value >= 0),
    user_id   uuid    not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (user_id, nutrient)
);
comment on table macros.macros_reference is 'arga:person';

create table macros.macros_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'macros.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table macros.macros_outbox is 'arga:person';

create index macros_outbox_pending on macros.macros_outbox (id) where published_at is null;
create index macros_outbox_metric
    on macros.macros_outbox ((payload #>> '{metric,day}'), (payload #>> '{metric,key}'), id desc)
    where type = 'macros.metric';

create table macros.macros_settings (
    user_id     uuid        primary key
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    protein_at  time        not null default '20:00',
    updated_at  timestamptz not null default now()
);
comment on table macros.macros_settings is 'arga:person';

alter table macros.macros_item drop constraint if exists macros_item_basis_per_check;
alter table macros.macros_item
    add constraint macros_item_basis_per_check check (basis_per in ('100g', 'serving', 'unit'));

create table macros.macros_goal (
    id          uuid    primary key default gen_random_uuid(),
    valid_from  date    not null,
    profile     text    not null default 'any' check (profile in ('any', 'training', 'rest')),
    nutrient    text    not null check (nutrient ~ '^[a-z][a-z0-9_]*$'),
    basis       text    not null default 'amount' check (basis in ('amount', 'kcal_pct', 'default')),
    min         numeric(10, 3) check (min is null or min >= 0),
    max         numeric(10, 3) check (max is null or max >= 0),
    created_at  timestamptz not null default now(),
    user_id     uuid    not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, profile, nutrient, valid_from),
    constraint macros_goal_ordered check (min is null or max is null or min <= max),
    constraint macros_goal_share check (
        basis <> 'kcal_pct' or (coalesce(min, 0) <= 100 and coalesce(max, 0) <= 100)
    ),
    constraint macros_goal_default_is_empty check (
        basis <> 'default' or (min is null and max is null)
    )
);
comment on table macros.macros_goal is 'arga:person';

create index macros_goal_by_day on macros.macros_goal (user_id, nutrient, profile, valid_from desc);

create table macros.macros_day_kind (
    day      date not null,
    kind     text not null check (kind in ('training', 'rest')),
    user_id  uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (user_id, day)
);
comment on table macros.macros_day_kind is 'arga:person';

alter table macros.macros_entry
    add column if not exists status text not null default 'confirmed'
        check (status in ('confirmed', 'planned'));

create index if not exists macros_entry_planned on macros.macros_entry (user_id, day)
    where status = 'planned';

create table macros.macros_template (
    id          uuid    primary key default gen_random_uuid(),
    name        text    not null check (length(btrim(name)) > 0 and length(name) <= 80),
    items       jsonb   not null check (jsonb_typeof(items) = 'array'),
    said        text    check (said is null or length(said) <= 1000),
    daily_at    time,
    created_at  timestamptz not null default now(),
    user_id     uuid    not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table macros.macros_template is 'arga:person';

create unique index macros_template_name on macros.macros_template (user_id, lower(btrim(name)));

create table macros.macros_template_run (
    template_id  uuid not null references macros.macros_template (id) on delete cascade,
    day          date not null,
    entry_id     uuid references macros.macros_entry (id) on delete set null,
    user_id      uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (template_id, day)
);
comment on table macros.macros_template_run is 'arga:person';

create index if not exists macros_item_user_id_idx on macros.macros_item (user_id);
create index if not exists macros_template_run_entry_id_idx on macros.macros_template_run (entry_id);
create index if not exists macros_template_run_user_id_idx on macros.macros_template_run (user_id);

alter table macros.macros_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists macros_outbox_key on macros.macros_outbox (user_id, type, key, id desc)
    where key is not null;

alter table macros.macros_item
    add column if not exists portion text
        check (portion is null or length(btrim(portion)) between 1 and 40);

alter table macros.macros_item
    add column if not exists doubt text check (doubt is null or doubt in ('first', 'unsure'));

alter table macros.macros_goal drop constraint if exists macros_goal_basis_check;
alter table macros.macros_goal
    add constraint macros_goal_basis_check
        check (basis in ('amount', 'kcal_pct', 'default', 'per_kg'));

create table macros.macros_day_complete (
    day         date        not null,
    marked_at   timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (user_id, day)
);
comment on table macros.macros_day_complete is 'arga:person';

create function macros.macros_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('macros_outbox', '');
    return null;
end;
$$;

create trigger macros_outbox_notify after insert on macros.macros_outbox
    for each statement execute function macros.macros_outbox_notify();

alter table macros.macros_item add column if not exists dish text
    check (dish is null or (length(btrim(dish)) > 0 and length(dish) <= 120));
