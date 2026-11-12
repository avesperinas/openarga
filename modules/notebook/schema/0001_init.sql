create table notebook.notebook_folder (
    id          uuid        primary key default gen_random_uuid(),
    path        text        not null check (length(path) between 1 and 1000
                                            and path !~ '(^/|/$|//)'),
    path_key    text        not null,
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, path_key)
);
comment on table notebook.notebook_folder is 'arga:person';

create table notebook.notebook_note (
    id            uuid        primary key default gen_random_uuid(),
    folder        text        not null default '' check (folder !~ '(^/|/$|//)'),
    folder_key    text        not null default '',
    title         text        not null check (length(btrim(title)) between 1 and 200
                                              and title !~ '[/\\:\[\]#^|]'),
    title_key     text        not null,
    content       text        not null default '' check (length(content) <= 1000000),
    properties    jsonb       not null default '{}' check (jsonb_typeof(properties) = 'object'),
    search_text   text        not null default '',
    search        tsvector    generated always as (to_tsvector('simple', search_text)) stored,
    version       integer     not null default 1 check (version > 0),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    updated_by    text        not null default 'app' check (updated_by in ('app', 'tool', 'import')),
    deleted_at    timestamptz,
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table notebook.notebook_note is 'arga:person';

create unique index notebook_note_one_per_place
    on notebook.notebook_note (user_id, folder_key, title_key) where deleted_at is null;
create index notebook_note_by_title on notebook.notebook_note (title_key) where deleted_at is null;
create index notebook_note_by_folder on notebook.notebook_note (folder_key) where deleted_at is null;
create index notebook_note_recent on notebook.notebook_note (updated_at desc);
create index notebook_note_search on notebook.notebook_note using gin (search);

create table notebook.notebook_revision (
    id            uuid        primary key default gen_random_uuid(),
    note_id       uuid        not null references notebook.notebook_note (id) on delete cascade,
    folder        text        not null,
    title         text        not null,
    content       text        not null,
    written_by    text        not null check (written_by in ('app', 'tool', 'import')),
    written_at    timestamptz not null,
    replaced_by   text        not null check (replaced_by in ('app', 'tool', 'import')),
    replaced_at   timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table notebook.notebook_revision is 'arga:person';

create index notebook_revision_of_note on notebook.notebook_revision (note_id, replaced_at desc);

create table notebook.notebook_link (
    note_id       uuid        not null references notebook.notebook_note (id) on delete cascade,
    position      integer     not null check (position >= 0),
    line          integer     not null check (line >= 0),
    kind          text        not null check (kind in ('note', 'file', 'app')),
    target        text        not null,
    title_key     text        not null,
    folder_key    text,
    heading       text,
    alias         text,
    embed         boolean     not null default false,
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (note_id, position)
);
comment on table notebook.notebook_link is 'arga:person';

create index notebook_link_by_target on notebook.notebook_link (title_key);

create table notebook.notebook_tag (
    note_id   uuid not null references notebook.notebook_note (id) on delete cascade,
    tag       text not null check (length(tag) between 1 and 200),
    user_id   uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (note_id, tag)
);
comment on table notebook.notebook_tag is 'arga:person';

create index notebook_tag_by_tag on notebook.notebook_tag (tag);

create function notebook.resolve(target_title text, target_folder text, from_folder text)
returns uuid
language sql stable security invoker
as $$
    select n.id
    from notebook.notebook_note n
    where n.deleted_at is null
      and n.title_key = target_title
      and (target_folder is null
           or n.folder_key = target_folder
           or right(n.folder_key, length(target_folder) + 1) = '/' || target_folder)
    order by (n.folder_key = from_folder) desc, length(n.folder_key), n.folder_key
    limit 1
$$;

create table notebook.notebook_setting (
    id            uuid        primary key default gen_random_uuid(),
    daily_folder  text        not null default 'Diario' check (daily_folder !~ '(^/|/$|//)'),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id)
);
comment on table notebook.notebook_setting is 'arga:person';

create table notebook.notebook_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'notebook.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table notebook.notebook_outbox is 'arga:person';

create index notebook_outbox_pending on notebook.notebook_outbox (id) where published_at is null;

create table notebook.notebook_file (
    id            uuid        primary key default gen_random_uuid(),
    name          text        not null check (length(btrim(name)) between 1 and 200
                                              and name !~ '[/\\:\[\]#^|]'),
    name_key      text        not null,
    content_type  text        not null check (content_type ~ '^[a-z]+/[a-z0-9.+-]+$'),
    size          integer     not null check (size between 1 and 20971520),
    content       bytea       not null,
    sha256        text        not null check (sha256 ~ '^[0-9a-f]{64}$'),
    created_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint notebook_file_size_is_content check (size = octet_length(content)),
    unique (user_id, name_key)
);
comment on table notebook.notebook_file is 'arga:person';

alter table notebook.notebook_setting
    add column review_property text check (review_property is null
                                           or length(btrim(review_property)) between 1 and 200);

create table notebook.notebook_export (
    id          uuid        primary key default gen_random_uuid(),
    pushed_at   timestamptz,
    tried_at    timestamptz,
    outcome     text        check (outcome in ('ok', 'error', 'skipped', 'unconnected')),
    detail      text        check (detail is null or length(detail) <= 500),
    commit_url  text        check (commit_url is null or commit_url ~ '^https://github\.com/'),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id)
);
comment on table notebook.notebook_export is 'arga:person';

create table notebook.notebook_exported (
    path     text not null check (length(path) between 1 and 1200),
    sha256   text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    user_id  uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (user_id, path)
);
comment on table notebook.notebook_exported is 'arga:person';

create table notebook.notebook_mention (
    note_id   uuid not null references notebook.notebook_note (id) on delete cascade,
    target    text not null check (length(target) between 3 and 200),
    title     text not null,
    line      text not null default '',
    user_id   uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (note_id, target)
);
comment on table notebook.notebook_mention is 'arga:person';

create table notebook.notebook_record (
    id            uuid        primary key default gen_random_uuid(),
    app           text        not null check (app ~ '^[a-z][a-z0-9_]{1,40}$'),
    record_id     text        not null check (length(record_id) between 1 and 160),
    link_key      text        not null,
    app_name      text        not null check (length(btrim(app_name)) between 1 and 80),
    title         text        not null,
    kind          text        not null,
    href          text        not null,
    folder        text        not null default '',
    day           date,
    properties    jsonb       not null default '{}' check (jsonb_typeof(properties) = 'object'),
    body          text        not null default '',
    removed       boolean     not null default false,
    note_id       uuid        references notebook.notebook_note (id) on delete set null,
    placed_folder text,
    placed_title  text,
    seen_at       timestamptz not null,
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, app, record_id)
);
comment on table notebook.notebook_record is 'arga:person';

create index notebook_record_by_note on notebook.notebook_record (note_id);
create index notebook_record_by_link on notebook.notebook_record (link_key) where day is null;
create index notebook_record_by_day on notebook.notebook_record (day) where day is not null;

alter table notebook.notebook_note add column updated_app text;
alter table notebook.notebook_revision add column written_app text;
alter table notebook.notebook_revision add column replaced_app text;

create index if not exists notebook_link_user_id_idx on notebook.notebook_link (user_id);
create index if not exists notebook_mention_user_id_idx on notebook.notebook_mention (user_id);
create index if not exists notebook_revision_user_id_idx on notebook.notebook_revision (user_id);
create index if not exists notebook_tag_user_id_idx on notebook.notebook_tag (user_id);

alter table notebook.notebook_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists notebook_outbox_key on notebook.notebook_outbox (user_id, type, key, id desc)
    where key is not null;

create function notebook.notebook_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('notebook_outbox', '');
    return null;
end;
$$;

create trigger notebook_outbox_notify after insert on notebook.notebook_outbox
    for each statement execute function notebook.notebook_outbox_notify();
