create table planner.planner_calendar (
    id             uuid        primary key default gen_random_uuid(),
    name           text        not null check (length(btrim(name)) between 1 and 60),
    tone           smallint    not null check (tone between 1 and 10),
    origin         text        not null default 'own' check (origin in ('own', 'subscription')),
    visible        boolean     not null default true,
    position       integer     not null default 0,
    connection_id  uuid,
    created_at     timestamptz not null default now(),
    user_id        uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id       uuid,
    constraint planner_calendar_subscription_has_connection
        check ((origin = 'subscription') = (connection_id is not null))
);
comment on table planner.planner_calendar is 'arga:shared';

create unique index planner_calendar_one_per_connection
    on planner.planner_calendar (user_id, connection_id) where connection_id is not null;

create table planner.planner_event (
    id           uuid        primary key default gen_random_uuid(),
    calendar_id  uuid        not null references planner.planner_calendar (id),
    title        text        not null check (length(btrim(title)) between 1 and 200),
    all_day      boolean     not null default false,
    start_at     timestamptz,
    end_at       timestamptz,
    start_date   date,
    end_date     date,
    tz           text        not null check (length(tz) between 1 and 64),
    location     text        check (location is null or length(btrim(location)) between 1 and 300),
    notes        text        check (notes is null or length(notes) <= 8000),
    url          text        check (url is null or url ~ '^https?://'),
    rrule        text        check (rrule is null or rrule ~ '^FREQ='),
    status       text        not null default 'confirmed' check (status in ('confirmed', 'cancelled')),
    source       text        not null default 'app' check (source in ('app', 'tool')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    user_id      uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id     uuid,
    constraint planner_event_timed_or_all_day check (
        case when all_day
            then start_date is not null and end_date > start_date and start_at is null and end_at is null
            else start_at is not null and end_at >= start_at and start_date is null and end_date is null
        end
    )
);
comment on table planner.planner_event is 'arga:shared';

create index planner_event_timed on planner.planner_event (start_at, end_at) where not all_day;
create index planner_event_days on planner.planner_event (start_date, end_date) where all_day;
create index planner_event_series on planner.planner_event (calendar_id) where rrule is not null;

create table planner.planner_override (
    id              uuid        primary key default gen_random_uuid(),
    event_id        uuid        not null references planner.planner_event (id),
    original_start  timestamp   not null,
    cancelled       boolean     not null default false,
    start_at        timestamptz,
    end_at          timestamptz,
    start_date      date,
    end_date        date,
    title           text        check (title is null or length(btrim(title)) between 1 and 200),
    location        text        check (location is null or length(btrim(location)) between 1 and 300),
    notes           text        check (notes is null or length(notes) <= 8000),
    url             text        check (url is null or url ~ '^https?://'),
    updated_at      timestamptz not null default now(),
    user_id         uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id        uuid,
    constraint planner_override_moves_whole check (
        (start_at is null) = (end_at is null) and (start_date is null) = (end_date is null)
    )
);
comment on table planner.planner_override is 'arga:shared';

create unique index planner_override_once on planner.planner_override (event_id, original_start);

create table planner.planner_feed_event (
    id             uuid        primary key default gen_random_uuid(),
    connection_id  uuid        not null,
    uid            text        not null check (length(uid) between 1 and 500),
    fingerprint    text        not null,
    payload        jsonb       not null,
    removed        boolean     not null default false,
    updated_at     timestamptz not null default now(),
    user_id        uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table planner.planner_feed_event is 'arga:person';

create unique index planner_feed_event_once on planner.planner_feed_event (user_id, connection_id, uid);

create table planner.planner_feed_hidden (
    id              uuid        primary key default gen_random_uuid(),
    connection_id   uuid        not null,
    uid             text        not null,
    original_start  timestamp   not null,
    created_at      timestamptz not null default now(),
    user_id         uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table planner.planner_feed_hidden is 'arga:person';

create unique index planner_feed_hidden_once
    on planner.planner_feed_hidden (user_id, connection_id, uid, original_start);

create table planner.planner_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'planner.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table planner.planner_outbox is 'arga:person';

create index planner_outbox_pending on planner.planner_outbox (id) where published_at is null;

alter table planner.planner_calendar
    drop constraint planner_calendar_origin_check,
    add constraint planner_calendar_origin_check
        check (origin in ('own', 'subscription', 'app'));

alter table planner.planner_calendar add column app text;

alter table planner.planner_calendar add constraint planner_calendar_app_has_app
    check ((origin = 'app') = (app is not null));

create unique index planner_calendar_one_per_app
    on planner.planner_calendar (user_id, app) where app is not null;

create table planner.planner_app_event (
    id           uuid        primary key default gen_random_uuid(),
    app          text        not null check (app ~ '^[a-z][a-z0-9_]{1,30}$'),
    uid          text        not null check (length(uid) between 1 and 500),
    payload      jsonb       not null,
    version_ts   timestamptz not null,
    updated_at   timestamptz not null default now(),
    user_id      uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table planner.planner_app_event is 'arga:person';

create unique index planner_app_event_once on planner.planner_app_event (user_id, uid);

alter table planner.planner_calendar
    add column display text not null default 'events'
        check (display in ('events', 'background'));

alter table planner.planner_app_event add column seen_at timestamptz;

alter table planner.planner_app_event
    add column if not exists layer text check (layer is null or length(layer) between 1 and 40);

create index if not exists planner_event_user_id_idx on planner.planner_event (user_id);
create index if not exists planner_override_user_id_idx on planner.planner_override (user_id);

alter table planner.planner_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists planner_outbox_key on planner.planner_outbox (user_id, type, key, id desc)
    where key is not null;

alter table planner.planner_calendar
    add column if not exists days_off_from uuid[] not null default '{}'
        check (cardinality(days_off_from) <= 20);

create function planner.planner_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('planner_outbox', '');
    return null;
end;
$$;

create trigger planner_outbox_notify after insert on planner.planner_outbox
    for each statement execute function planner.planner_outbox_notify();

update planner.planner_calendar set name = 'KPIs'
 where origin = 'app' and app = 'goals' and name = 'Goals';
