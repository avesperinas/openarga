create table outings.outings_wish (
    id             uuid        primary key default gen_random_uuid(),
    kind           text        not null check (kind in ('eat', 'plan', 'getaway', 'trip')),
    name           text        not null check (length(btrim(name)) between 1 and 120),
    body           text        check (body is null or length(btrim(body)) between 1 and 4000),
    place_name     text        check (place_name is null or length(btrim(place_name)) between 1 and 200),
    place_detail   text        check (place_detail is null or length(place_detail) <= 300),
    place_town     text        check (place_town is null or length(place_town) <= 120),
    place_country  text        check (place_country is null or length(place_country) <= 120),
    place_country_code text    check (place_country_code is null or place_country_code ~ '^[A-Z]{2}$'),
    lat            double precision check (lat between -90 and 90),
    lon            double precision check (lon between -180 and 180),
    osm_ref        text        check (osm_ref is null or osm_ref ~ '^(node|way|relation)/[0-9]+$'),
    done_at        timestamptz,
    source         text        not null default 'app' check (source in ('app', 'tool')),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    user_id        uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint outings_wish_place_named check (place_name is not null or (lat is null and osm_ref is null)),
    constraint outings_wish_located check ((lat is null) = (lon is null))
);
comment on table outings.outings_wish is 'arga:person';

create index outings_wish_pending on outings.outings_wish (created_at desc) where done_at is null;

create table outings.outings_photo (
    wish_id        uuid        primary key references outings.outings_wish (id) on delete cascade,
    content        bytea       not null,
    content_type   text        not null check (content_type in ('image/jpeg', 'image/png', 'image/webp')),
    thumb          bytea       not null,
    updated_at     timestamptz not null default now(),
    user_id        uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint outings_photo_size check (octet_length(content) <= 2 * 1024 * 1024)
);
comment on table outings.outings_photo is 'arga:person';

create table outings.outings_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'outings.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table outings.outings_outbox is 'arga:person';

create index outings_outbox_pending on outings.outings_outbox (id) where published_at is null;

create table outings.outings_event (
    id            uuid        primary key default gen_random_uuid(),
    title         text        not null check (length(btrim(title)) between 1 and 200),
    starts_on     date        not null,
    ends_on       date        not null,
    start_time    text        check (start_time is null or start_time ~ '^[0-9]{1,2}:[0-9]{2}$'),
    venue         text        check (venue is null or length(venue) <= 200),
    town          text        check (town is null or length(town) <= 120),
    category      text        not null check (category in ('eat', 'stage', 'culture', 'festival', 'outdoors')),
    summary       text        check (summary is null or length(summary) <= 400),
    links         jsonb       not null default '[]'::jsonb,
    recurring     boolean     not null default false,
    in_calendar   boolean     not null default false,
    hidden        boolean     not null default false,
    first_seen    timestamptz not null default now(),
    last_seen     timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint outings_event_in_order check (ends_on >= starts_on)
);
comment on table outings.outings_event is 'arga:person';

create index outings_event_by_day on outings.outings_event (starts_on, ends_on) where not hidden;

create table outings.outings_event_source (
    id            uuid        primary key default gen_random_uuid(),
    event_id      uuid        not null references outings.outings_event (id),
    connection    uuid        not null,
    key           text        not null check (length(key) between 1 and 100),
    fingerprint   text        not null,
    payload       jsonb       not null,
    removed       boolean     not null default false,
    first_seen    timestamptz not null default now(),
    last_seen     timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, connection, key)
);
comment on table outings.outings_event_source is 'arga:person';

create index outings_event_source_of on outings.outings_event_source (event_id);

create table outings.outings_venue (
    id            uuid        primary key default gen_random_uuid(),
    name          text        not null check (length(name) between 1 and 200),
    town          text        not null default '' check (length(town) <= 120),
    lat           double precision check (lat between -90 and 90),
    lon           double precision check (lon between -180 and 180),
    found         boolean     not null,
    asked_at      timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, name, town),
    constraint outings_venue_located check (found = (lat is not null and lon is not null))
);
comment on table outings.outings_venue is 'arga:person';

alter table outings.outings_wish
    add column event_id uuid references outings.outings_event (id),
    add column starts_on date,
    add column ends_on date,
    add constraint outings_wish_dated check (
        (starts_on is null and ends_on is null) or (starts_on is not null and ends_on >= starts_on)
    );

create unique index outings_wish_one_per_event on outings.outings_wish (user_id, event_id)
    where event_id is not null;

alter table outings.outings_event_source
    add column alone boolean not null default false;

create table outings.outings_recurring (
    id               uuid        primary key default gen_random_uuid(),
    name             text        not null check (length(btrim(name)) between 1 and 200),
    key              text        not null check (length(key) between 1 and 200),
    month            smallint    not null check (month between 1 and 12),
    notify           boolean     not null default false,
    last_event_id    uuid        references outings.outings_event (id),
    last_starts_on   date,
    dated_at         timestamptz,
    created_at       timestamptz not null default now(),
    user_id          uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, key)
);
comment on table outings.outings_recurring is 'arga:person';

alter table outings.outings_event_source
    alter column connection drop not null,
    add column origin text not null default 'hub' check (origin in ('hub', 'tool')),
    add constraint outings_event_source_origin check ((origin = 'hub') = (connection is not null));

create unique index outings_event_source_by_hand
    on outings.outings_event_source (user_id, key) where connection is null;

alter table outings.outings_event
    add column programme jsonb not null default '[]'::jsonb,
    add column highlight boolean not null default false,
    add column dismissed_at timestamptz;

create table outings.outings_interest (
    id          uuid        primary key default gen_random_uuid(),
    kind        text        not null check (kind in ('like', 'mute')),
    term        text        not null check (length(btrim(term)) between 2 and 80),
    folded      text        not null check (length(folded) between 2 and 80),
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, kind, folded)
);
comment on table outings.outings_interest is 'arga:person';

alter table outings.outings_photo
    add column credit_author  text check (credit_author is null or length(credit_author) <= 200),
    add column credit_license text check (credit_license is null or length(credit_license) <= 80),
    add column credit_page    text check (credit_page is null or credit_page ~ '^https://');

alter table outings.outings_wish
    add column place_photo_at timestamptz;

alter table outings.outings_wish
    add column place_photo_none boolean;

alter table outings.outings_wish add column if not exists space_id uuid;
alter table outings.outings_photo add column if not exists space_id uuid;

comment on table outings.outings_wish is 'arga:shared';
comment on table outings.outings_photo is 'arga:shared';

create index if not exists outings_event_user_id_idx on outings.outings_event (user_id);
create index if not exists outings_photo_user_id_idx on outings.outings_photo (user_id);
create index if not exists outings_recurring_last_event_id_idx on outings.outings_recurring (last_event_id);
create index if not exists outings_wish_event_id_idx on outings.outings_wish (event_id);

alter table outings.outings_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists outings_outbox_key on outings.outings_outbox (user_id, type, key, id desc)
    where key is not null;

create function outings.outings_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('outings_outbox', '');
    return null;
end;
$$;

create trigger outings_outbox_notify after insert on outings.outings_outbox
    for each statement execute function outings.outings_outbox_notify();

drop table if exists outings.outings_recurring;
