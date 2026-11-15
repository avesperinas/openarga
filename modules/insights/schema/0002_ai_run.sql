create table insights.insights_ended (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null
                            default nullif(current_setting('arga.user_id', true), '')::uuid,
    key         text        not null check (length(key) between 1 and 160),
    outcome     text        not null check (outcome in ('ok', 'failed', 'rate_limited')),
    detail      text        check (detail is null or length(detail) <= 500),
    code        text        check (code is null or length(code) <= 40),
    ran_with    text        check (ran_with is null or length(ran_with) <= 120),
    ended_at    timestamptz not null default now(),
    unique (user_id, key)
);
comment on table insights.insights_ended is 'arga:person';

create index insights_ended_recent on insights.insights_ended (user_id, ended_at desc);
