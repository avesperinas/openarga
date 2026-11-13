alter table hub.ai_attempt drop constraint if exists ai_attempt_status_check;
alter table hub.ai_attempt add constraint ai_attempt_status_check
    check (status in ('queued', 'running', 'done', 'failed', 'over_budget'));

alter table hub.ai_attempt add column if not exists task text
    check (length(task) between 1 and 20000);
alter table hub.ai_attempt add column if not exists web boolean not null default false;
alter table hub.ai_attempt add column if not exists max_steps integer not null default 30
    check (max_steps between 1 and 100);

create unique index if not exists ai_attempt_one_run_per_key
    on hub.ai_attempt (user_id, app, run_key)
    where capability = 'run' and status in ('queued', 'running', 'done');

create index if not exists ai_attempt_queued
    on hub.ai_attempt (started_at) where status = 'queued';
