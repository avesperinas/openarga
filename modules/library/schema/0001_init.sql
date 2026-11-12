create table library.library_edition (
    id            uuid        primary key default gen_random_uuid(),
    isbn13        text        check (isbn13 ~ '^97[89][0-9]{10}$'),
    title         text        not null check (length(btrim(title)) between 1 and 300),
    subtitle      text        check (subtitle is null or length(btrim(subtitle)) between 1 and 300),
    authors       text[]      not null default '{}',
    pages         integer     check (pages > 0 and pages < 20000),
    language      text        check (language ~ '^[a-z]{2}$'),
    year          smallint    check (year between 1400 and 2200),
    subjects      text[]      not null default '{}',
    cover         bytea,
    cover_type    text        check (cover_type in ('image/jpeg', 'image/png', 'image/webp')),
    source        text        not null check (source in ('openlibrary', 'google_books')),
    source_ref    text        not null check (length(btrim(source_ref)) > 0),
    fetched_at    timestamptz not null default now(),
    user_id       uuid        default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint library_edition_cover_typed check ((cover is null) = (cover_type is null)),
    constraint library_edition_once_per_source unique nulls not distinct (user_id, source, source_ref)
);
comment on table library.library_edition is 'arga:catalog';

create unique index library_edition_by_isbn
    on library.library_edition ((coalesce(user_id, '00000000-0000-0000-0000-000000000000'::uuid)), isbn13)
    where isbn13 is not null;

create table library.library_manual_edition (
    id            uuid        primary key default gen_random_uuid(),
    isbn13        text        check (isbn13 ~ '^97[89][0-9]{10}$'),
    title         text        not null check (length(btrim(title)) between 1 and 300),
    subtitle      text        check (subtitle is null or length(btrim(subtitle)) between 1 and 300),
    authors       text[]      not null default '{}',
    pages         integer     check (pages > 0 and pages < 20000),
    language      text        check (language ~ '^[a-z]{2}$'),
    year          smallint    check (year between 1400 and 2200),
    cover         bytea,
    cover_type    text        check (cover_type in ('image/jpeg', 'image/png', 'image/webp')),
    created_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint library_manual_edition_cover_typed check ((cover is null) = (cover_type is null))
);
comment on table library.library_manual_edition is 'arga:person';

create table library.library_reading (
    id                 uuid        primary key default gen_random_uuid(),
    edition_id         uuid        references library.library_edition (id),
    manual_edition_id  uuid        references library.library_manual_edition (id),
    status             text        not null
                                   check (status in ('want', 'reading', 'read', 'abandoned')),
    started_on         date,
    finished_on        date,
    rating             numeric(2, 1) check (rating between 0 and 5 and rating * 2 = trunc(rating * 2)),
    format             text        not null default 'paper'
                                   check (format in ('paper', 'ebook', 'audio')),
    genre              text        not null default 'other'
                                   check (genre in ('novel', 'essay', 'history', 'science',
                                                    'biography', 'business', 'fantasy_scifi',
                                                    'crime', 'poetry', 'comic', 'other')),
    note               text        check (note is null or length(btrim(note)) between 1 and 2000),
    source             text        not null default 'app' check (source in ('app', 'tool')),
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    user_id            uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint library_reading_one_edition
        check ((edition_id is null) <> (manual_edition_id is null)),
    constraint library_reading_want_has_no_dates
        check (status <> 'want' or (started_on is null and finished_on is null)),
    constraint library_reading_reading_has_started
        check (status <> 'reading' or (started_on is not null and finished_on is null)),
    constraint library_reading_read_has_both
        check (status <> 'read' or (started_on is not null and finished_on is not null)),
    constraint library_reading_abandoned_has_started
        check (status <> 'abandoned' or started_on is not null),
    constraint library_reading_in_order
        check (finished_on is null or started_on is null or finished_on >= started_on)
);
comment on table library.library_reading is 'arga:person';

create index library_reading_by_status on library.library_reading (status);
create index library_reading_finished on library.library_reading (finished_on desc)
    where finished_on is not null;

create table library.library_goal (
    id       uuid     primary key default gen_random_uuid(),
    year     smallint not null check (year between 2000 and 2200),
    books    smallint not null check (books between 1 and 1000),
    user_id  uuid     not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, year)
);
comment on table library.library_goal is 'arga:person';

create table library.library_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'library.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table library.library_outbox is 'arga:person';

create index library_outbox_pending on library.library_outbox (id) where published_at is null;

create function library.library_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('library_outbox', '');
    return null;
end;
$$;

create trigger library_outbox_notify after insert on library.library_outbox
    for each statement execute function library.library_outbox_notify();

create index if not exists library_manual_edition_user_id_idx on library.library_manual_edition (user_id);
create index if not exists library_reading_edition_id_idx on library.library_reading (edition_id);
create index if not exists library_reading_manual_edition_id_idx on library.library_reading (manual_edition_id);
create index if not exists library_reading_user_id_idx on library.library_reading (user_id);

alter table library.library_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists library_outbox_key on library.library_outbox (user_id, type, key, id desc)
    where key is not null;
