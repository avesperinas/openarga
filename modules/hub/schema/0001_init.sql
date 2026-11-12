create table hub.hub_connection (
    id                  uuid        primary key default gen_random_uuid(),
    user_id             uuid        not null
                                    default nullif(current_setting('arga.user_id', true), '')::uuid,
    provider            text        not null check (provider ~ '^[a-z][a-z0-9_]{1,40}$'),
    label               text        not null check (length(btrim(label)) between 1 and 80),
    config              jsonb       not null default '{}',
    status              text        not null default 'active'
                                    check (status in ('pending', 'active')),
    paused              boolean     not null default false,
    consent_expires_at  timestamptz,
    auth_state          text        unique,
    created_at          timestamptz not null default now()
);
comment on table hub.hub_connection is 'arga:person';

create index hub_connection_per_person on hub.hub_connection (user_id, provider);

create table hub.hub_credential (
    user_id        uuid        not null
                               default nullif(current_setting('arga.user_id', true), '')::uuid,
    connection_id  uuid        not null
                               references hub.hub_connection (id) on delete cascade,
    key            text        not null check (key ~ '^[a-z][a-z0-9_]{1,60}$'),
    ciphertext     bytea       not null,
    hint           text        not null,
    created_at     timestamptz not null default now(),
    last_used_at   timestamptz,
    primary key (user_id, connection_id, key)
);
comment on table hub.hub_credential is 'arga:person';

create table hub.hub_run (
    id               uuid        primary key default gen_random_uuid(),
    user_id          uuid        not null
                                 default nullif(current_setting('arga.user_id', true), '')::uuid,
    connection_id    uuid        not null
                                 references hub.hub_connection (id) on delete cascade,
    capability       text        not null check (capability in ('sync', 'action', 'lookup')),
    operation        text        not null check (operation ~ '^[a-z][a-z0-9_]{1,40}$'),
    idempotency_key  text        check (length(idempotency_key) between 1 and 200),
    started_at       timestamptz not null default now(),
    finished_at      timestamptz,
    outcome          text        not null default 'running'
                                 check (outcome in ('running', 'ok', 'error', 'skipped',
                                                    'rate_limited')),
    emitted          integer     not null default 0 check (emitted >= 0),
    detail           text        check (length(detail) <= 1000)
);
comment on table hub.hub_run is 'arga:person';

create index hub_run_latest on hub.hub_run (connection_id, started_at desc);
create unique index hub_run_once
    on hub.hub_run (user_id, connection_id, idempotency_key)
    where idempotency_key is not null;

alter table hub.hub_run drop constraint hub_run_capability_check;
alter table hub.hub_run add constraint hub_run_capability_check
    check (capability in ('sync', 'action', 'lookup', 'push'));

alter table hub.hub_connection add column plugs jsonb not null default '{}';

create table hub.hub_claude_grant_request (
    state          text        primary key check (length(state) between 20 and 100),
    user_id        uuid        not null
                               default nullif(current_setting('arga.user_id', true), '')::uuid,
    connection_id  uuid        not null
                               references hub.hub_connection (id) on delete cascade,
    app            text        not null check (app ~ '^[a-z][a-z0-9_]*$'),
    verifier       text        not null check (length(verifier) between 43 and 128),
    created_at     timestamptz not null default now()
);
comment on table hub.hub_claude_grant_request is 'arga:person';

create table hub.hub_claude_job (
    id             uuid        primary key default gen_random_uuid(),
    user_id        uuid        not null
                               default nullif(current_setting('arga.user_id', true), '')::uuid,
    run_id         uuid        not null references hub.hub_run (id) on delete cascade,
    connection_id  uuid        not null
                               references hub.hub_connection (id) on delete cascade,
    app            text        not null check (app ~ '^[a-z][a-z0-9_]*$'),
    prompt         text        not null check (length(prompt) between 1 and 40000),
    tools          text[]      not null default '{}'
                               check (tools <@ array['WebSearch', 'WebFetch']::text[]),
    status         text        not null default 'queued'
                               check (status in ('queued', 'running', 'done')),
    created_at     timestamptz not null default now(),
    started_at     timestamptz,
    finished_at    timestamptz
);
comment on table hub.hub_claude_job is 'arga:person';

create index hub_claude_job_queued on hub.hub_claude_job (status, created_at);

alter table hub.hub_claude_job
    add column wait_for_room boolean not null default false;

alter table hub.hub_claude_job
    add column not_before timestamptz;

create index if not exists hub_claude_grant_request_connection_id_idx on hub.hub_claude_grant_request (connection_id);
create index if not exists hub_claude_grant_request_user_id_idx on hub.hub_claude_grant_request (user_id);
create index if not exists hub_claude_job_connection_id_idx on hub.hub_claude_job (connection_id);
create index if not exists hub_claude_job_run_id_idx on hub.hub_claude_job (run_id);
create index if not exists hub_claude_job_user_id_idx on hub.hub_claude_job (user_id);
create index if not exists hub_credential_connection_id_idx on hub.hub_credential (connection_id);

alter table hub.hub_claude_job
    add column if not exists ran_on uuid
        references hub.hub_connection (id) on delete set null;

create index if not exists hub_claude_job_ran_on_idx
    on hub.hub_claude_job (ran_on);

alter table hub.hub_run
    add column if not exists code text check (code is null or code ~ '^[a-z][a-z0-9_]{1,40}$');
