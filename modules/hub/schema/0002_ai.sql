create table hub.ai_settings (
    user_id         uuid        primary key
                                default nullif(current_setting('arga.user_id', true), '')::uuid,
    provider        text        check (provider in ('none', 'fake', 'anthropic', 'openai')),
    base_url        text        check (base_url ~ '^https?://' and length(base_url) <= 300),
    fast_model      text        check (length(btrim(fast_model)) between 1 and 120),
    smart_model     text        check (length(btrim(smart_model)) between 1 and 120),
    monthly_tokens  bigint      check (monthly_tokens >= 0),
    key_ciphertext  bytea,
    key_hint        text,
    updated_at      timestamptz not null default now()
);
comment on table hub.ai_settings is 'arga:person';

create table hub.ai_attempt (
    id             uuid        primary key default gen_random_uuid(),
    user_id        uuid        not null
                               default nullif(current_setting('arga.user_id', true), '')::uuid,
    app            text        not null check (app ~ '^[a-z][a-z0-9_]{1,30}$'),
    capability     text        not null check (capability in ('extract', 'run')),
    role           text        not null check (role in ('fast', 'smart')),
    provider       text        not null check (length(provider) between 1 and 40),
    model          text        not null check (length(model) between 1 and 120),
    run_key        text        check (length(run_key) between 1 and 120),
    status         text        not null
                               check (status in ('running', 'done', 'failed', 'over_budget')),
    steps          integer     not null default 0 check (steps >= 0),
    input_tokens   bigint      not null default 0 check (input_tokens >= 0),
    output_tokens  bigint      not null default 0 check (output_tokens >= 0),
    detail         text        check (length(detail) <= 2000),
    summary        text        check (length(summary) <= 4000),
    started_at     timestamptz not null default now(),
    finished_at    timestamptz
);
comment on table hub.ai_attempt is 'arga:person';

create index ai_attempt_user_started on hub.ai_attempt (user_id, started_at desc);
