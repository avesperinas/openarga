create table insights.insights_profile (
    user_id     uuid        primary key
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    name        text        check (name is null or length(btrim(name)) between 1 and 24),
    about       text        not null default '' check (length(about) <= 8000),
    updated_at  timestamptz not null default now()
);
comment on table insights.insights_profile is 'arga:person';

create table insights.insights_insight (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    kind        text        not null check (kind in ('alert', 'weekly')),
    domain      text        not null
                            check (domain in ('money', 'body', 'time', 'leisure', 'cross')),
    topic       text        not null check (topic ~ '^[a-z0-9][a-z0-9._:-]{1,79}$'),
    title       text        not null check (length(btrim(title)) between 1 and 120),
    body        text        not null check (length(btrim(body)) between 1 and 6000),
    figures     jsonb       not null check (jsonb_typeof(figures) = 'array'
                                            and jsonb_array_length(figures) > 0),
    affects     text        not null check (length(btrim(affects)) between 3 and 300),
    action      text        not null check (length(btrim(action)) between 10 and 600),
    created_at  timestamptz not null default now(),
    read_at     timestamptz,
    rating      text        check (rating in ('useful', 'known', 'not_applicable')),
    rated_at    timestamptz
);
comment on table insights.insights_insight is 'arga:person';

create index insights_insight_recent on insights.insights_insight (user_id, created_at desc);
create index insights_insight_topic on insights.insights_insight (user_id, topic, created_at desc);

create table insights.insights_thread (
    id             uuid        primary key default gen_random_uuid(),
    user_id        uuid        not null
                               default nullif(current_setting('arga.user_id', true), '')::uuid,
    insight_id     uuid        references insights.insights_insight (id) on delete set null,
    title          text        not null check (length(btrim(title)) between 1 and 120),
    waiting_since  timestamptz,
    problem        text        check (problem is null or length(problem) <= 500),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
comment on table insights.insights_thread is 'arga:person';

create index insights_thread_recent on insights.insights_thread (user_id, updated_at desc);

create table insights.insights_message (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    thread_id   uuid        not null references insights.insights_thread (id) on delete cascade,
    author      text        not null check (author in ('person', 'insights')),
    body        text        not null check (length(btrim(body)) between 1 and 12000),
    created_at  timestamptz not null default now()
);
comment on table insights.insights_message is 'arga:person';

create index insights_message_thread on insights.insights_message (thread_id, created_at);

create table insights.insights_run (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    kind        text        not null check (kind in ('morning', 'weekly')),
    key         text        not null check (key ~ '^(morning|weekly):[0-9W-]{7,10}$'),
    outcome     text        not null check (outcome in ('queued', 'quiet', 'refused')),
    detail      text        check (detail is null or length(detail) <= 500),
    signal_ids  jsonb       not null default '[]'::jsonb check (jsonb_typeof(signal_ids) = 'array'),
    asked_at    timestamptz not null default now(),
    unique (user_id, key)
);
comment on table insights.insights_run is 'arga:person';

create index insights_run_recent on insights.insights_run (user_id, asked_at desc);

create index if not exists insights_message_user_id_idx on insights.insights_message (user_id);
create index if not exists insights_thread_insight_id_idx on insights.insights_thread (insight_id);

alter table insights.insights_run
    add column if not exists attempt smallint not null default 1 check (attempt between 1 and 9);

alter table insights.insights_insight
    add column proposals jsonb not null default '[]'
        check (jsonb_typeof(proposals) = 'array' and jsonb_array_length(proposals) <= 7);

create table insights.insights_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'insights.%'),
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
comment on table insights.insights_outbox is 'arga:person';

create index insights_outbox_pending on insights.insights_outbox (id) where published_at is null;
create index insights_outbox_key on insights.insights_outbox (user_id, type, key, id desc)
    where key is not null;

create function insights.insights_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('insights_outbox', '');
    return null;
end;
$$;

create trigger insights_outbox_notify after insert on insights.insights_outbox
    for each statement execute function insights.insights_outbox_notify();

alter table insights.insights_profile
    add column if not exists pill_on boolean not null default true,
    add column if not exists pill_time time not null default '09:00',
    add column if not exists pill_minutes smallint not null default 15
        check (pill_minutes in (5, 10, 15, 20, 30)),
    add column if not exists pill_language text
        check (pill_language is null or pill_language ~ '^[a-z]{2}$'),
    add column if not exists pill_level text
        check (pill_level is null or pill_level in ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')),
    add column if not exists questions text not null default 'sometimes'
        check (questions in ('never', 'sometimes', 'daily')),
    add column if not exists started_at timestamptz;

create table insights.insights_trait (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    facet       text        not null check (facet in (
                    'topic', 'genre', 'format', 'creator', 'work', 'style', 'avoid', 'context',
                    'language')),
    key         text        not null check (key ~ '^[a-z0-9][a-z0-9 _.:-]{0,119}$'),
    label       text        not null check (length(btrim(label)) between 1 and 120),
    stance      smallint    not null default 1 check (stance between -2 and 2),
    source      text        not null check (source in ('said', 'answered', 'seen', 'rated')),
    evidence    text        check (evidence is null or length(evidence) <= 300),
    status      text        not null default 'proposed'
                            check (status in ('proposed', 'confirmed', 'rejected')),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (user_id, facet, key)
);
comment on table insights.insights_trait is 'arga:person';

create table insights.insights_question (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    origin      text        not null check (origin in ('start', 'pass')),
    bank_key    text        check (bank_key is null or bank_key ~ '^[a-z][a-z_.]{1,40}$'),
    kind        text        not null check (kind in ('one', 'many', 'scale', 'either', 'confirm', 'free')),
    text        text        not null check (length(btrim(text)) between 3 and 200),
    why         text        check (why is null or length(why) <= 200),
    options     jsonb       not null default '[]'::jsonb check (jsonb_typeof(options) = 'array'),
    topic       text        check (topic is null or topic ~ '^[a-z0-9][a-z0-9._:-]{1,79}$'),
    trait_id    uuid        references insights.insights_trait (id) on delete set null,
    asked_at    timestamptz not null default now(),
    answer      jsonb,
    answered_at timestamptz,
    skipped_at  timestamptz,
    seen_at     timestamptz
);
comment on table insights.insights_question is 'arga:person';

create unique index insights_question_bank on insights.insights_question (user_id, bank_key)
    where bank_key is not null;
create index insights_question_recent on insights.insights_question (user_id, asked_at desc);

create table insights.insights_family (
    id           uuid        primary key default gen_random_uuid(),
    user_id      uuid        not null
                             default nullif(current_setting('arga.user_id', true), '')::uuid,
    key          text        not null check (key ~ '^[a-z][a-z0-9_]{1,30}$'),
    name         text        not null check (length(btrim(name)) between 1 and 40),
    hue          smallint    not null check (hue between 1 and 8),
    glyph        text        not null check (glyph ~ '^[a-z][a-z0-9-]{1,30}$'),
    themes       text        not null check (length(themes) <= 500),
    weight       smallint    not null default 1 check (weight between 0 and 3),
    outside      boolean     not null default false,
    position     smallint    not null default 0,
    created_at   timestamptz not null default now(),
    unique (user_id, key)
);
comment on table insights.insights_family is 'arga:person';

create table insights.insights_source (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    family_key  text        not null check (family_key ~ '^[a-z][a-z0-9_]{1,30}$'),
    name        text        not null check (length(btrim(name)) between 1 and 80),
    kind        text        not null check (kind in (
                    'magazine', 'blog', 'podcast', 'video', 'forum', 'media', 'reference')),
    language    text        not null default 'es' check (language ~ '^[a-z]{2}$'),
    url         text        not null check (url ~ '^https://\S+$' and length(url) <= 300),
    builtin     boolean     not null default false,
    hidden      boolean     not null default false,
    created_at  timestamptz not null default now(),
    unique (user_id, family_key, name)
);
comment on table insights.insights_source is 'arga:person';

create table insights.insights_craft_run (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    kind        text        not null check (kind in ('pill', 'more', 'picks', 'profile')),
    key         text        not null check (key ~ '^(pill|more|picks|profile):[0-9A-Za-z:-]{3,60}$'),
    outcome     text        not null check (outcome in ('queued', 'refused', 'quiet')),
    detail      text        check (detail is null or length(detail) <= 500),
    attempt     smallint    not null default 1 check (attempt between 1 and 9),
    origin      text        check (origin is null or origin in ('daily', 'surprise', 'branch')),
    parent_id   uuid,
    branch      text        check (branch is null or length(branch) <= 200),
    family_key  text,
    asked_at    timestamptz not null default now(),
    unique (user_id, key)
);
comment on table insights.insights_craft_run is 'arga:person';

create index insights_craft_run_recent on insights.insights_craft_run (user_id, asked_at desc);

create table insights.insights_pill (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    day         date        not null,
    origin      text        not null check (origin in ('daily', 'surprise', 'branch')),
    run_key     text,
    parent_id   uuid        references insights.insights_pill (id) on delete set null,
    depth       smallint    not null default 0 check (depth between 0 and 20),
    family_key  text        not null check (family_key ~ '^[a-z][a-z0-9_]{1,30}$'),
    topic       text        not null check (length(btrim(topic)) between 2 and 120),
    hook        text        check (hook is null or length(hook) <= 200),
    language    text        not null default 'es' check (language ~ '^[a-z]{2}$'),
    minutes     smallint    not null check (minutes between 3 and 40),
    headline    text        not null check (length(btrim(headline)) between 5 and 160),
    lead        text        not null check (length(btrim(lead)) between 20 and 800),
    sections    jsonb       not null check (jsonb_typeof(sections) = 'array'
                                            and jsonb_array_length(sections) between 2 and 6),
    to_tell     text        not null check (length(btrim(to_tell)) between 20 and 600),
    to_think    text        check (to_think is null or length(to_think) <= 400),
    branches    jsonb       not null default '[]'::jsonb check (jsonb_typeof(branches) = 'array'),
    sources     jsonb       not null check (jsonb_typeof(sources) = 'array'
                                            and jsonb_array_length(sources) between 1 and 6),
    glossary    jsonb       not null default '[]'::jsonb check (jsonb_typeof(glossary) = 'array'),
    reaction    text        check (reaction is null or reaction in ('interested', 'known', 'other')),
    read_at     timestamptz,
    created_at  timestamptz not null default now()
);
comment on table insights.insights_pill is 'arga:person';

create index insights_pill_recent on insights.insights_pill (user_id, created_at desc);
create index insights_pill_day on insights.insights_pill (user_id, day, origin);

create table insights.insights_fact (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    day         date        not null,
    family_key  text        not null check (family_key ~ '^[a-z][a-z0-9_]{1,30}$'),
    text        text        not null check (length(btrim(text)) between 30 and 400),
    detail      text        check (detail is null or length(detail) <= 1200),
    source      jsonb       not null check (jsonb_typeof(source) = 'object'),
    reaction    text        check (reaction is null or reaction in ('interested', 'known')),
    created_at  timestamptz not null default now()
);
comment on table insights.insights_fact is 'arga:person';

create index insights_fact_day on insights.insights_fact (user_id, day desc, created_at);

create table insights.insights_pick (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    kind        text        not null check (kind in (
                    'book', 'podcast', 'episode', 'film', 'series', 'documentary', 'video',
                    'article', 'course')),
    key         text        not null check (length(key) between 1 and 200),
    title       text        not null check (length(btrim(title)) between 1 and 200),
    creators    jsonb       not null default '[]'::jsonb check (jsonb_typeof(creators) = 'array'),
    year        smallint    check (year is null or year between 1000 and 2200),
    length      text        check (length is null or length(length) <= 40),
    language    text        check (language is null or language ~ '^[a-z]{2}$'),
    why         text        not null check (length(btrim(why)) between 10 and 400),
    because     jsonb       not null default '[]'::jsonb check (jsonb_typeof(because) = 'array'),
    origin      text        not null check (origin in ('pill', 'weekly', 'event', 'chat')),
    pill_id     uuid        references insights.insights_pill (id) on delete set null,
    verified    text        not null check (verified in ('catalog', 'link')),
    ref         jsonb       not null default '{}'::jsonb check (jsonb_typeof(ref) = 'object'),
    links       jsonb       not null default '[]'::jsonb check (jsonb_typeof(links) = 'array'),
    state       text        not null default 'new'
                            check (state in ('new', 'saved', 'doing', 'done', 'dismissed')),
    collections jsonb       not null default '[]'::jsonb check (jsonb_typeof(collections) = 'array'),
    rating      numeric(2, 1) check (rating is null or (rating between 0 and 5 and rating * 2 = round(rating * 2))),
    more_like   boolean,
    note        text        check (note is null or length(note) <= 600),
    sent_to     text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (user_id, kind, key)
);
comment on table insights.insights_pick is 'arga:person';

create index insights_pick_recent on insights.insights_pick (user_id, created_at desc);

create table insights.insights_pick_cover (
    pick_id     uuid        primary key references insights.insights_pick (id) on delete cascade,
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    content     bytea       not null,
    type        text        not null check (type in ('image/jpeg', 'image/png', 'image/webp'))
);
comment on table insights.insights_pick_cover is 'arga:person';

create index insights_question_trait on insights.insights_question (trait_id);
create index insights_pill_parent on insights.insights_pill (parent_id);
create index insights_pick_pill on insights.insights_pick (pill_id);
create index insights_pick_cover_owner on insights.insights_pick_cover (user_id);

create table insights.insights_pill_audio (
    pill_id     uuid        primary key references insights.insights_pill (id) on delete cascade,
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    content     bytea       not null,
    type        text        not null check (type in ('audio/mpeg')),
    duration    real        not null check (duration > 0),
    timeline    jsonb       not null check (jsonb_typeof(timeline) = 'array'),
    voice       text        not null check (length(voice) between 1 and 80),
    created_at  timestamptz not null default now()
);
comment on table insights.insights_pill_audio is 'arga:person';

create index insights_pill_audio_owner on insights.insights_pill_audio (user_id);
