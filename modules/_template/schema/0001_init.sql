create table __MODULE_ID__.__MODULE_ID___readings (
    id          uuid primary key default gen_random_uuid(),
    ts          timestamptz not null default now(),
    label       text        not null check (length(label) between 1 and 40),
    value       numeric     not null,
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table __MODULE_ID__.__MODULE_ID___readings is 'arga:person';

create index __MODULE_ID___readings_by_person on __MODULE_ID__.__MODULE_ID___readings (user_id, ts desc);

create table __MODULE_ID__.__MODULE_ID___targets (
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    label       text        not null check (length(label) between 1 and 40),
    value       numeric     not null,
    updated_at  timestamptz not null default now(),
    primary key (user_id, label)
);
comment on table __MODULE_ID__.__MODULE_ID___targets is 'arga:person';

create table __MODULE_ID__.__MODULE_ID___outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like '__MODULE_ID__.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    key           text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored,
    unique (user_id, dedup_hash)
);
comment on table __MODULE_ID__.__MODULE_ID___outbox is 'arga:person';

create index __MODULE_ID___outbox_pending on __MODULE_ID__.__MODULE_ID___outbox (id) where published_at is null;
create index __MODULE_ID___outbox_key on __MODULE_ID__.__MODULE_ID___outbox (user_id, type, key, id desc)
    where key is not null;

create function __MODULE_ID__.__MODULE_ID___outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('__MODULE_ID___outbox', '');
    return null;
end;
$$;

create trigger __MODULE_ID___outbox_notify after insert on __MODULE_ID__.__MODULE_ID___outbox
    for each statement execute function __MODULE_ID__.__MODULE_ID___outbox_notify();
