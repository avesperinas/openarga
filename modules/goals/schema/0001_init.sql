create table goals.goals_category (
    id          uuid        primary key default gen_random_uuid(),
    name        text        not null check (length(btrim(name)) between 1 and 40),
    hue         smallint    not null check (hue between 1 and 8),
    position    integer     not null default 0,
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id    uuid
);
comment on table goals.goals_category is 'arga:shared';

create table goals.goals_task (
    id           uuid        primary key default gen_random_uuid(),
    category_id  uuid        not null references goals.goals_category (id) on delete cascade,
    title        text        not null check (length(btrim(title)) between 1 and 200),
    notes        text        check (notes is null or length(notes) <= 4000),
    due_on       date,
    due_time     time,
    rule         text        check (rule is null or length(rule) between 6 and 300),
    series_on    date,
    previous_id  uuid        references goals.goals_task (id) on delete set null,
    done_at      timestamptz,
    done_by      uuid,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    user_id      uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id     uuid,
    constraint goals_task_time_needs_day check (due_time is null or due_on is not null),
    constraint goals_task_rule_needs_day check ((rule is null) = (series_on is null) and (rule is null or due_on is not null)),
    constraint goals_task_done_by_whom check ((done_at is null) = (done_by is null))
);
comment on table goals.goals_task is 'arga:shared';

create index goals_task_pending on goals.goals_task (due_on nulls last, created_at)
    where done_at is null;
create index goals_task_done on goals.goals_task (category_id, done_at desc)
    where done_at is not null;
create index goals_task_by_previous on goals.goals_task (previous_id)
    where previous_id is not null;

create table goals.goals_person (
    user_id    uuid        primary key default nullif(current_setting('arga.user_id', true), '')::uuid,
    seeded_at  timestamptz not null default now()
);
comment on table goals.goals_person is 'arga:person';

create table goals.goals_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'goals.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table goals.goals_outbox is 'arga:person';

create index goals_outbox_pending on goals.goals_outbox (id) where published_at is null;

create table goals.goals_goal (
    id              uuid        primary key default gen_random_uuid(),
    category_id     uuid        references goals.goals_category (id) on delete set null,
    title           text        not null check (length(btrim(title)) between 1 and 120),
    kind            text        not null check (kind in ('periodic', 'dated')),
    metric_key      text        check (metric_key is null or length(metric_key) between 3 and 160),
    metric_label    text        check (metric_label is null or length(metric_label) <= 80),
    metric_unit     text        check (metric_unit is null or length(metric_unit) <= 16),
    metric_kind     text        check (metric_kind is null or metric_kind in ('level', 'amount')),
    direction       text        not null default 'at_least'
                                check (direction in ('at_least', 'at_most')),
    target          numeric,
    period          text        check (period is null or period in ('day', 'week')),
    days_per_week   smallint    check (days_per_week is null or days_per_week between 1 and 7),
    start_value     numeric,
    start_on        date        not null,
    due_on          date,
    status          text        not null default 'active'
                                check (status in ('active', 'achieved', 'missed', 'abandoned')),
    closed_on       date,
    closed_value    numeric,
    note            text        check (note is null or length(note) <= 2000),
    featured        boolean     not null default false,
    position        integer     not null default 0,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    user_id         uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint goals_goal_periodic_shape check (
        kind <> 'periodic' or (
            period is not null
            and (period <> 'day' or days_per_week is not null)
            and (period <> 'week' or target is not null)
            and due_on is null
        )
    ),
    constraint goals_goal_dated_shape check (kind <> 'dated' or (due_on is not null and period is null)),
    constraint goals_goal_metric_whole check (
        (metric_key is null) = (metric_kind is null)
    ),
    constraint goals_goal_closed check ((status = 'active') = (closed_on is null))
);
comment on table goals.goals_goal is 'arga:person';

create index goals_goal_active on goals.goals_goal (position, created_at) where status = 'active';
create index goals_goal_by_metric on goals.goals_goal (metric_key) where metric_key is not null;

create table goals.goals_goal_check (
    id          uuid        primary key default gen_random_uuid(),
    goal_id     uuid        not null references goals.goals_goal (id) on delete cascade,
    day         date        not null,
    done        boolean,
    value       numeric,
    note        text        check (note is null or length(note) <= 500),
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (goal_id, day),
    constraint goals_goal_check_says_something check (done is not null or value is not null)
);
comment on table goals.goals_goal_check is 'arga:person';

alter table goals.goals_person add column goals_seeded_at timestamptz;

create index if not exists goals_category_user_id_idx on goals.goals_category (user_id);
create index if not exists goals_goal_category_id_idx on goals.goals_goal (category_id);
create index if not exists goals_goal_user_id_idx on goals.goals_goal (user_id);
create index if not exists goals_goal_check_user_id_idx on goals.goals_goal_check (user_id);
create index if not exists goals_task_user_id_idx on goals.goals_task (user_id);

alter table goals.goals_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists goals_outbox_key on goals.goals_outbox (user_id, type, key, id desc)
    where key is not null;

create function goals.goals_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('goals_outbox', '');
    return null;
end;
$$;

create trigger goals_outbox_notify after insert on goals.goals_outbox
    for each statement execute function goals.goals_outbox_notify();
