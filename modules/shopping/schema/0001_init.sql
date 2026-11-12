create table shopping.shopping_category (
    id        text     primary key check (id ~ '^[a-z][a-z_]*$'),
    name      text     not null check (length(btrim(name)) > 0),
    emoji     text     not null check (length(btrim(emoji)) > 0),
    position  smallint not null check (position > 0),
    user_id   uuid     default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table shopping.shopping_category is 'arga:catalog';

insert into shopping.shopping_category (id, name, emoji, position, user_id) values
    ('produce',   'Fruta y verdura',       '🥬',  1, null),
    ('bakery',    'Panadería',             '🥖',  2, null),
    ('meat',      'Carne',                 '🥩',  3, null),
    ('fish',      'Pescado',               '🐟',  4, null),
    ('deli',      'Charcutería y quesos',  '🧀',  5, null),
    ('dairy',     'Lácteos y huevos',      '🥛',  6, null),
    ('pantry',    'Despensa',              '🥫',  7, null),
    ('breakfast', 'Desayuno y dulces',     '🍪',  8, null),
    ('frozen',    'Congelados',            '🧊',  9, null),
    ('drinks',    'Bebidas',               '🍷', 10, null),
    ('cleaning',  'Limpieza',              '🧽', 11, null),
    ('hygiene',   'Higiene',               '🧴', 12, null),
    ('other',     'Otros',                 '🛒', 13, null);

create table shopping.shopping_product (
    id           uuid        primary key default gen_random_uuid(),
    name         text        not null check (length(btrim(name)) between 1 and 80),
    key          text        not null check (length(key) > 0),
    category_id  text        not null references shopping.shopping_category (id),
    quantity     text        check (quantity is null or length(btrim(quantity)) between 1 and 30),
    created_at   timestamptz not null default now(),
    user_id      uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id     uuid
);
comment on table shopping.shopping_product is 'arga:shared';

create unique index shopping_product_once
    on shopping.shopping_product ((coalesce(space_id, user_id)), key);

create table shopping.shopping_trip (
    id           uuid        primary key default gen_random_uuid(),
    finished_at  timestamptz not null default now(),
    items        smallint    not null check (items > 0),
    user_id      uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id     uuid
);
comment on table shopping.shopping_trip is 'arga:shared';

create index shopping_trip_recent on shopping.shopping_trip (finished_at desc);

create table shopping.shopping_item (
    id          uuid        primary key default gen_random_uuid(),
    product_id  uuid        not null references shopping.shopping_product (id),
    quantity    text        check (quantity is null or length(btrim(quantity)) between 1 and 30),
    note        text        check (note is null or length(btrim(note)) between 1 and 120),
    status      text        not null default 'pending'
                            check (status in ('pending', 'in_cart', 'bought', 'dropped')),
    source      text        not null default 'app' check (source in ('app', 'tool')),
    added_at    timestamptz not null default now(),
    checked_at  timestamptz,
    closed_at   timestamptz,
    trip_id     uuid        references shopping.shopping_trip (id),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id    uuid,
    constraint shopping_item_bought_in_a_trip check ((status = 'bought') = (trip_id is not null)),
    constraint shopping_item_closed_when_out
        check ((status in ('bought', 'dropped')) = (closed_at is not null)),
    constraint shopping_item_checked_in_cart
        check (status <> 'in_cart' or checked_at is not null)
);
comment on table shopping.shopping_item is 'arga:shared';

create unique index shopping_item_open_once on shopping.shopping_item (product_id)
    where status in ('pending', 'in_cart');

create index shopping_item_by_trip on shopping.shopping_item (trip_id) where trip_id is not null;
create index shopping_item_bought on shopping.shopping_item (product_id, closed_at)
    where status = 'bought';

create table shopping.shopping_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'shopping.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table shopping.shopping_outbox is 'arga:person';

create index shopping_outbox_pending on shopping.shopping_outbox (id) where published_at is null;

create table if not exists shopping.shopping_setting (
    user_id        uuid        primary key
                               default nullif(current_setting('arga.user_id', true), '')::uuid,
    list_space_id  uuid,
    updated_at     timestamptz not null default now()
);
comment on table shopping.shopping_setting is 'arga:person';

alter table shopping.shopping_category no force row level security;

update shopping.shopping_category set user_id = null
where id in ('produce', 'bakery', 'meat', 'fish', 'deli', 'dairy', 'pantry', 'breakfast',
             'frozen', 'drinks', 'cleaning', 'hygiene', 'other');

alter table shopping.shopping_category force row level security;

create function shopping.shopping_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('shopping_outbox', '');
    return null;
end;
$$;

create trigger shopping_outbox_notify after insert on shopping.shopping_outbox
    for each statement execute function shopping.shopping_outbox_notify();

create index if not exists shopping_category_user_id_idx on shopping.shopping_category (user_id);
create index if not exists shopping_item_user_id_idx on shopping.shopping_item (user_id);
create index if not exists shopping_product_category_id_idx on shopping.shopping_product (category_id);
create index if not exists shopping_product_user_id_idx on shopping.shopping_product (user_id);
create index if not exists shopping_trip_user_id_idx on shopping.shopping_trip (user_id);

alter table shopping.shopping_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists shopping_outbox_key on shopping.shopping_outbox (user_id, type, key, id desc)
    where key is not null;
