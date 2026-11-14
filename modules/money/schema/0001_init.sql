create table money.money_v1_setting (
    user_id      uuid        primary key
                             default nullif(current_setting('arga.user_id', true), '')::uuid,
    cutoff       date,
    me_name      text        not null default 'Yo' check (length(me_name) between 1 and 40),
    other_name   text        not null default 'La otra persona' check (length(other_name) between 1 and 40),
    holders      text[]      not null default '{}',
    window_days  smallint    not null default 4 check (window_days between 1 and 15),
    revision     bigint      not null default 0,
    updated_at   timestamptz not null default now()
);
comment on table money.money_v1_setting is 'arga:person';

create table money.money_v1_account (
    id                 uuid          primary key default gen_random_uuid(),
    user_id            uuid          not null
                                     default nullif(current_setting('arga.user_id', true), '')::uuid,
    key                text          not null check (key ~ '^[a-z0-9_]{1,40}$'),
    name               text          not null check (length(name) between 1 and 80),
    institution        text          not null check (length(institution) between 1 and 80),
    type               text          not null check (length(type) between 1 and 40),
    movements          text          not null check (movements in ('api', 'statement', 'matched', 'manual')),
    value              text          check (value in ('balance', 'computed', 'snapshot', 'manual')),
    ownership          numeric(5,4)  not null default 1 check (ownership > 0 and ownership <= 1),
    counts_for_savings boolean,
    spending           boolean,
    shared_space       boolean       not null default false,
    aliases            text[]        not null default '{}',
    ibans              text[]        not null default '{}',
    match_bank         text,
    match_key          text,
    position           integer       not null default 0,
    unique (user_id, key)
);
comment on table money.money_v1_account is 'arga:person';

create table money.money_v1_category (
    id          uuid      primary key default gen_random_uuid(),
    user_id     uuid      not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    nature      text      not null check (nature in ('income', 'expense')),
    ownership   text      not null check (ownership in ('individual', 'shared')),
    name        text      not null check (length(name) between 1 and 60),
    split       text      check (split in ('fifty_fifty', 'proportional')),
    extended    boolean   not null default false,
    position    integer   not null default 0,
    check ((ownership = 'shared') = (split is not null)),
    unique (user_id, nature, ownership, name)
);
comment on table money.money_v1_category is 'arga:person';

create table money.money_v1_rule (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    position    integer     not null,
    spec        jsonb       not null check (jsonb_typeof(spec) = 'object'),
    origin      text        not null default 'import' check (origin in ('import', 'merchant')),
    created_at  timestamptz not null default now()
);
comment on table money.money_v1_rule is 'arga:person';
create index money_v1_rule_position on money.money_v1_rule (user_id, position);

create table money.money_v1_label (
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    fact_id     text        not null check (length(fact_id) between 1 and 300),
    spec        jsonb       not null check (jsonb_typeof(spec) = 'object'),
    updated_at  timestamptz not null default now(),
    primary key (user_id, fact_id)
);
comment on table money.money_v1_label is 'arga:person';

create table money.money_v1_entry (
    id           uuid          primary key default gen_random_uuid(),
    user_id      uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    payer        text          not null check (payer in ('me', 'other')),
    on_date      date          not null,
    amount       numeric(14,2) not null check (amount > 0),
    description  text          not null check (length(description) between 1 and 120),
    category_id  uuid          not null references money.money_v1_category (id),
    created_at   timestamptz   not null default now()
);
comment on table money.money_v1_entry is 'arga:person';

create table money.money_v1_income (
    id         uuid          primary key default gen_random_uuid(),
    user_id    uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    person     text          not null check (person in ('me', 'other')),
    from_on    date          not null,
    to_on      date          not null check (to_on >= from_on),
    salary     numeric(12,2) not null check (salary >= 0),
    extra      numeric(12,2) not null default 0 check (extra >= 0)
);
comment on table money.money_v1_income is 'arga:person';

create table money.money_v1_year (
    user_id   uuid     not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    year      smallint not null check (year between 2000 and 2100),
    settled   boolean  not null default false,
    primary key (user_id, year)
);
comment on table money.money_v1_year is 'arga:person';

create table money.money_v1_history (
    id         uuid          primary key default gen_random_uuid(),
    user_id    uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    year       smallint      not null,
    month      smallint      not null check (month between 1 and 12),
    kind       text          not null check (kind in ('expense', 'deposit')),
    amount     numeric(14,2) not null,
    category   text,
    split      text          check (split in ('fifty_fifty', 'proportional')),
    payer      text          check (payer in ('account', 'me', 'other'))
);
comment on table money.money_v1_history is 'arga:person';
create index money_v1_history_year on money.money_v1_history (user_id, year);

create table money.money_v1_history_flow (
    id         uuid          primary key default gen_random_uuid(),
    user_id    uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    year       smallint      not null check (year between 2000 and 2100),
    month      smallint      not null check (month between 1 and 12),
    kind       text          not null check (kind in ('income', 'expense', 'contribution')),
    amount     numeric(14,2) not null,
    category   text,
    account    text,
    mine       boolean       not null default true,
    note       text,
    check ((kind = 'contribution') = (account is not null))
);
comment on table money.money_v1_history_flow is 'arga:person';
create index money_v1_history_flow_year on money.money_v1_history_flow (user_id, year);

create table money.money_v1_valuation (
    id         uuid          primary key default gen_random_uuid(),
    user_id    uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    account    text          not null check (length(account) between 1 and 40),
    on_date    date          not null,
    value      numeric(14,2) not null,
    source     text          not null default 'manual' check (source in ('history', 'manual')),
    unique (user_id, account, on_date)
);
comment on table money.money_v1_valuation is 'arga:person';

alter table money.money_v1_account
    add column if not exists role text check (role in ('emergency_fund'));

alter table money.money_v1_category
    add column if not exists not_living boolean not null default false,
    add column if not exists not_basic boolean not null default false;

alter table money.money_v1_setting
    add column if not exists emergency_months smallint not null default 3
        check (emergency_months between 1 and 24);

drop table if exists money.money_account cascade;
drop table if exists money.money_accrual cascade;
drop table if exists money.money_bank_handoff cascade;
drop table if exists money.money_category cascade;
drop table if exists money.money_claim_refused cascade;
drop table if exists money.money_connection cascade;
drop table if exists money.money_credential cascade;
drop table if exists money.money_cutover cascade;
drop table if exists money.money_deposit cascade;
drop table if exists money.money_feed cascade;
drop table if exists money.money_goal cascade;
drop table if exists money.money_handoff cascade;
drop table if exists money.money_history_month cascade;
drop table if exists money.money_holding cascade;
drop table if exists money.money_institution cascade;
drop table if exists money.money_member cascade;
drop table if exists money.money_member_iban cascade;
drop table if exists money.money_member_income cascade;
drop table if exists money.money_movement cascade;
drop table if exists money.money_nature_rule cascade;
drop table if exists money.money_outbox cascade;
drop table if exists money.money_plan cascade;
drop table if exists money.money_refund_link cascade;
drop table if exists money.money_rule cascade;
drop table if exists money.money_setting cascade;
drop table if exists money.money_settlement cascade;
drop table if exists money.money_share cascade;
drop table if exists money.money_shared_category cascade;
drop table if exists money.money_share_funding cascade;
drop table if exists money.money_share_rule cascade;
drop table if exists money.money_share_skip cascade;
drop table if exists money.money_share_template cascade;
drop table if exists money.money_space_config cascade;
drop table if exists money.money_transfer cascade;
drop table if exists money.money_transfer_rejected cascade;
drop table if exists money.money_valuation cascade;

alter table money.money_v1_setting add column if not exists space_id uuid;

create table money.money_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'money.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table money.money_outbox is 'arga:person';

create index money_outbox_pending on money.money_outbox (id) where published_at is null;

create table if not exists money.money_v1_common_month (
    user_id          uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id         uuid          not null,
    year             smallint      not null check (year between 2000 and 2100),
    month            smallint      not null check (month between 1 and 12),
    source           text          not null check (source in ('history', 'book')),
    by_category      jsonb         not null default '{}'::jsonb,
    split_of         jsonb         not null default '{}'::jsonb,
    paid_account     numeric(14,2) not null default 0,
    paid_keeper      numeric(14,2) not null default 0,
    paid_other       numeric(14,2) not null default 0,
    deposits_keeper  numeric(14,2) not null default 0,
    deposits_other   numeric(14,2) not null default 0,
    updated_at       timestamptz   not null default now(),
    primary key (space_id, user_id, year, month)
);
comment on table money.money_v1_common_month is 'arga:shared';

create table if not exists money.money_v1_common_year (
    user_id       uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id      uuid          not null,
    year          smallint      not null check (year between 2000 and 2100),
    ratio_keeper  numeric(7,6)  not null check (ratio_keeper between 0 and 1),
    settled       boolean       not null default false,
    keeper_name   text          not null check (length(keeper_name) between 1 and 40),
    other_name    text          not null check (length(other_name) between 1 and 40),
    updated_at    timestamptz   not null default now(),
    primary key (space_id, user_id, year)
);
comment on table money.money_v1_common_year is 'arga:shared';

create table if not exists money.money_v1_common_category (
    user_id   uuid      not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id  uuid      not null,
    name      text      not null check (length(name) between 1 and 60),
    split     text      not null check (split in ('fifty_fifty', 'proportional')),
    position  smallint  not null default 0,
    primary key (space_id, user_id, name)
);
comment on table money.money_v1_common_category is 'arga:shared';

create table if not exists money.money_v1_common_entry (
    id           uuid          primary key default gen_random_uuid(),
    user_id      uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id     uuid          not null,
    paid_by      uuid,
    on_date      date          not null,
    amount       numeric(14,2) not null check (amount > 0),
    description  text          not null check (length(description) between 1 and 120),
    category     text          not null check (length(category) between 1 and 60),
    origin_id    uuid          unique,
    created_at   timestamptz   not null default now()
);
comment on table money.money_v1_common_entry is 'arga:shared';
create index if not exists money_v1_common_entry_space
    on money.money_v1_common_entry (space_id, on_date);

create table if not exists money.money_v1_holding (
    id       uuid          primary key default gen_random_uuid(),
    user_id  uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    account  text          not null check (length(account) between 1 and 40),
    on_date  date          not null,
    symbol   text          not null check (length(symbol) between 1 and 160),
    name     text          not null check (length(name) between 1 and 120),
    value    numeric(14,2) not null check (value >= 0),
    unique (user_id, account, on_date, symbol)
);
comment on table money.money_v1_holding is 'arga:person';

create table if not exists money.money_v1_fund (
    user_id  uuid  not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    symbol   text  not null check (length(symbol) between 1 and 160),
    asset    text  not null
                   check (asset in ('equity', 'bond', 'real_estate', 'cash', 'crypto', 'other')),
    regions  jsonb not null default '{}'::jsonb,
    primary key (user_id, symbol)
);
comment on table money.money_v1_fund is 'arga:person';

create index if not exists money_v1_common_category_user_id_idx on money.money_v1_common_category (user_id);
create index if not exists money_v1_common_entry_user_id_idx on money.money_v1_common_entry (user_id);
create index if not exists money_v1_common_month_user_id_idx on money.money_v1_common_month (user_id);
create index if not exists money_v1_common_year_user_id_idx on money.money_v1_common_year (user_id);
create index if not exists money_v1_entry_category_id_idx on money.money_v1_entry (category_id);
create index if not exists money_v1_entry_user_id_idx on money.money_v1_entry (user_id);
create index if not exists money_v1_income_user_id_idx on money.money_v1_income (user_id);

alter table money.money_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists money_outbox_key on money.money_outbox (user_id, type, key, id desc)
    where key is not null;
