create table if not exists money.money_v1_statement_line (
    id          uuid          primary key default gen_random_uuid(),
    user_id     uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    account     text          not null check (length(account) between 1 and 40),
    reference   text          not null check (length(reference) between 1 and 120),
    booked_on   date          not null,
    value_on    date,
    amount      numeric(14,2) not null,
    description text          not null default '' check (length(description) <= 500),
    counterparty text         check (length(counterparty) <= 200),
    unique (user_id, account, reference)
);
comment on table money.money_v1_statement_line is 'arga:person';
create index if not exists money_v1_statement_line_user_id_idx on money.money_v1_statement_line (user_id);

create table if not exists money.money_v1_statement_balance (
    id       uuid          primary key default gen_random_uuid(),
    user_id  uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    account  text          not null check (length(account) between 1 and 40),
    on_date  date          not null,
    amount   numeric(14,2) not null,
    unique (user_id, account, on_date)
);
comment on table money.money_v1_statement_balance is 'arga:person';
create index if not exists money_v1_statement_balance_user_id_idx on money.money_v1_statement_balance (user_id);
