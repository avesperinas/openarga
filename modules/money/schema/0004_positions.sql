create table if not exists money.money_v1_position (
    id       uuid           primary key default gen_random_uuid(),
    user_id  uuid           not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    account  text           not null check (length(account) between 1 and 40),
    symbol   text           not null check (length(symbol) between 1 and 160),
    name     text           not null default '' check (length(name) <= 120),
    units    numeric(20,8)  not null check (units > 0),
    cost     numeric(14,2)  not null check (cost >= 0),
    price    numeric(18,6)  check (price is null or price >= 0),
    price_on date,
    unique (user_id, account, symbol)
);
comment on table money.money_v1_position is 'arga:person';
create index if not exists money_v1_position_user_id_idx on money.money_v1_position (user_id);
