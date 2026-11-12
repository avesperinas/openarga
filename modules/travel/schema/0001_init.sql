create table travel.travel_place (
    id            uuid        primary key default gen_random_uuid(),
    name          text        not null check (length(btrim(name)) between 1 and 120),
    display_name  text        check (display_name is null or length(display_name) <= 300),
    lat           double precision check (lat between -90 and 90),
    lon           double precision check (lon between -180 and 180),
    country_code  text        check (country_code is null or country_code ~ '^[A-Z]{2}$'),
    region_code   text        check (region_code is null or length(region_code) between 2 and 20),
    kind          text        check (kind is null or length(kind) <= 40),
    osm_type      text        check (osm_type is null or osm_type in ('node', 'way', 'relation')),
    osm_id        bigint,
    created_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint travel_place_both_or_none check ((lat is null) = (lon is null)),
    constraint travel_place_osm_whole check ((osm_type is null) = (osm_id is null))
);
comment on table travel.travel_place is 'arga:person';

create unique index travel_place_osm_once on travel.travel_place (user_id, osm_type, osm_id)
    where osm_id is not null;

create table travel.travel_trip (
    id          uuid        primary key default gen_random_uuid(),
    title       text        not null check (length(btrim(title)) between 1 and 120),
    starts_on   date        not null,
    ends_on     date        not null,
    travellers  smallint    not null default 1 check (travellers between 1 and 50),
    companions  text[]      not null default '{}',
    tags        text[]      not null default '{}',
    notes       text        check (notes is null or length(notes) <= 4000),
    source      text        not null default 'app' check (source in ('app', 'tool')),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint travel_trip_in_order check (ends_on >= starts_on)
);
comment on table travel.travel_trip is 'arga:person';

create index travel_trip_by_date on travel.travel_trip (starts_on desc);

create table travel.travel_stay (
    id             uuid        primary key default gen_random_uuid(),
    trip_id        uuid        not null references travel.travel_trip (id) on delete cascade,
    place_id       uuid        not null references travel.travel_place (id),
    arrives_on     date        not null,
    leaves_on      date        not null,
    accommodation  text        check (accommodation is null or length(accommodation) <= 200),
    user_id        uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint travel_stay_in_order check (leaves_on >= arrives_on)
);
comment on table travel.travel_stay is 'arga:person';

create index travel_stay_by_trip on travel.travel_stay (trip_id, arrives_on);

create table travel.travel_visit (
    id          uuid        primary key default gen_random_uuid(),
    trip_id     uuid        not null references travel.travel_trip (id) on delete cascade,
    place_id    uuid        not null references travel.travel_place (id),
    stay_id     uuid        references travel.travel_stay (id) on delete set null,
    visited_on  date,
    note        text        check (note is null or length(note) <= 500),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table travel.travel_visit is 'arga:person';

create index travel_visit_by_trip on travel.travel_visit (trip_id, visited_on);

create table travel.travel_leg (
    id             uuid        primary key default gen_random_uuid(),
    trip_id        uuid        not null references travel.travel_trip (id) on delete cascade,
    from_place_id  uuid        not null references travel.travel_place (id),
    to_place_id    uuid        not null references travel.travel_place (id),
    travelled_on   date,
    mode           text        not null check (mode in ('plane', 'train', 'car', 'bus', 'boat')),
    km             numeric(8, 1) check (km is null or km >= 0),
    note           text        check (note is null or length(note) <= 500),
    user_id        uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table travel.travel_leg is 'arga:person';

create index travel_leg_by_trip on travel.travel_leg (trip_id, travelled_on);

create table travel.travel_expense (
    id           uuid          primary key default gen_random_uuid(),
    trip_id      uuid          not null references travel.travel_trip (id) on delete cascade,
    category     text          not null check (category in ('transport', 'lodging', 'other')),
    concept      text          not null check (length(btrim(concept)) between 1 and 60),
    amount_eur   numeric(10, 2) not null check (amount_eur >= 0),
    note         text          check (note is null or length(note) <= 300),
    source       text          not null default 'app' check (source in ('app', 'tool')),
    created_at   timestamptz   not null default now(),
    user_id      uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table travel.travel_expense is 'arga:person';

create index travel_expense_by_trip on travel.travel_expense (trip_id, category);

create table travel.travel_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'travel.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table travel.travel_outbox is 'arga:person';

create index travel_outbox_pending on travel.travel_outbox (id) where published_at is null;

create table travel.travel_other_place (
    id          uuid        primary key default gen_random_uuid(),
    place_id    uuid        not null references travel.travel_place (id),
    note        text        check (note is null or length(note) <= 300),
    source      text        not null default 'app' check (source in ('app', 'tool')),
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table travel.travel_other_place is 'arga:person';

create unique index travel_other_place_once on travel.travel_other_place (user_id, place_id);

alter table travel.travel_trip add column archived_at timestamptz;

create table travel.travel_home (
    id          uuid        primary key default gen_random_uuid(),
    place_id    uuid        not null references travel.travel_place (id),
    updated_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table travel.travel_home is 'arga:person';

create unique index travel_home_once on travel.travel_home (user_id);

alter table travel.travel_leg add column on_map boolean;

alter table travel.travel_place add column if not exists space_id uuid;
alter table travel.travel_trip add column if not exists space_id uuid;
alter table travel.travel_stay add column if not exists space_id uuid;
alter table travel.travel_visit add column if not exists space_id uuid;
alter table travel.travel_leg add column if not exists space_id uuid;
alter table travel.travel_expense add column if not exists space_id uuid;

comment on table travel.travel_place is 'arga:shared';
comment on table travel.travel_trip is 'arga:shared';
comment on table travel.travel_stay is 'arga:shared';
comment on table travel.travel_visit is 'arga:shared';
comment on table travel.travel_leg is 'arga:shared';
comment on table travel.travel_expense is 'arga:shared';

create index if not exists travel_trip_by_space on travel.travel_trip (space_id)
    where space_id is not null;

alter table travel.travel_trip
    add column if not exists status text not null default 'confirmed'
        check (status in ('plan', 'confirmed'));

create table if not exists travel.travel_block (
    id          uuid        primary key default gen_random_uuid(),
    trip_id     uuid        not null references travel.travel_trip (id) on delete cascade,
    day         date,
    position    integer     not null default 0,
    kind        text        not null default 'activity'
                            check (kind in ('activity', 'transport', 'meal', 'accommodation',
                                            'free_time', 'other')),
    title       text        not null check (length(btrim(title)) between 1 and 120),
    starts_at   time,
    ends_at     time,
    place_id    uuid        references travel.travel_place (id) on delete set null,
    visit_id    uuid        unique references travel.travel_visit (id) on delete cascade,
    notes       text        check (notes is null or length(notes) <= 2000),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id    uuid,
    check (ends_at is null or starts_at is null or ends_at >= starts_at)
);
comment on table travel.travel_block is 'arga:shared';

create index if not exists travel_block_by_day on travel.travel_block (trip_id, day, position);

alter table travel.travel_stay
    add column if not exists check_in_at time,
    add column if not exists check_out_at time,
    add column if not exists address text check (address is null or length(address) <= 300),
    add column if not exists confirmation text
        check (confirmation is null or length(confirmation) <= 60),
    add column if not exists provider text check (provider is null or length(provider) <= 80),
    add column if not exists booking_url text
        check (booking_url is null or length(booking_url) <= 500);

alter table travel.travel_leg
    add column if not exists departs_at time,
    add column if not exists arrives_on date,
    add column if not exists arrives_at time,
    add column if not exists carrier text check (carrier is null or length(carrier) <= 80),
    add column if not exists number text check (number is null or length(number) <= 20),
    add column if not exists from_code text check (from_code is null or length(from_code) <= 10),
    add column if not exists to_code text check (to_code is null or length(to_code) <= 10),
    add column if not exists terminal text check (terminal is null or length(terminal) <= 20),
    add column if not exists seat text check (seat is null or length(seat) <= 20),
    add column if not exists confirmation text
        check (confirmation is null or length(confirmation) <= 60),
    add column if not exists provider text check (provider is null or length(provider) <= 80),
    add column if not exists booking_url text
        check (booking_url is null or length(booking_url) <= 500);

alter table travel.travel_block
    add column if not exists confirmation text
        check (confirmation is null or length(confirmation) <= 60),
    add column if not exists provider text check (provider is null or length(provider) <= 80),
    add column if not exists booking_url text
        check (booking_url is null or length(booking_url) <= 500);

alter table travel.travel_expense
    add column if not exists stay_id uuid references travel.travel_stay (id) on delete set null,
    add column if not exists leg_id uuid references travel.travel_leg (id) on delete set null,
    add column if not exists block_id uuid references travel.travel_block (id) on delete set null;

create unique index if not exists travel_expense_of_stay on travel.travel_expense (stay_id)
    where stay_id is not null;
create unique index if not exists travel_expense_of_leg on travel.travel_expense (leg_id)
    where leg_id is not null;
create unique index if not exists travel_expense_of_block on travel.travel_expense (block_id)
    where block_id is not null;

create table if not exists travel.travel_tile (
    z           smallint    not null check (z between 0 and 15),
    x           integer     not null check (x >= 0),
    y           integer     not null check (y >= 0),
    data        bytea,
    build       text,
    fetched_at  timestamptz not null default now(),
    primary key (z, x, y)
);
comment on table travel.travel_tile is 'arga:system';

create table if not exists travel.travel_idea (
    id            uuid        primary key default gen_random_uuid(),
    title         text        not null check (length(btrim(title)) between 1 and 120),
    notes         text        check (notes is null or length(notes) <= 4000),
    budget_eur    numeric(10, 2) check (budget_eur is null or budget_eur >= 0),
    days_min      smallint    check (days_min is null or days_min between 1 and 365),
    days_max      smallint    check (days_max is null or days_max between 1 and 365),
    months        smallint[]  not null default '{}'
                              check (months <@ array[1,2,3,4,5,6,7,8,9,10,11,12]::smallint[]),
    tags          text[]      not null default '{}',
    archived_at   timestamptz,
    source        text        not null default 'app' check (source in ('app', 'tool')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id      uuid,
    check (days_min is null or days_max is null or days_max >= days_min)
);
comment on table travel.travel_idea is 'arga:shared';

create table if not exists travel.travel_idea_place (
    id          uuid        primary key default gen_random_uuid(),
    idea_id     uuid        not null references travel.travel_idea (id) on delete cascade,
    place_id    uuid        not null references travel.travel_place (id),
    position    integer     not null default 0,
    note        text        check (note is null or length(note) <= 500),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id    uuid,
    unique (idea_id, place_id)
);
comment on table travel.travel_idea_place is 'arga:shared';

alter table travel.travel_trip
    add column if not exists idea_id uuid references travel.travel_idea (id) on delete set null;

alter table travel.travel_trip
    add column if not exists budget_eur numeric(10, 2) check (budget_eur is null or budget_eur >= 0);

create table if not exists travel.travel_traveller (
    id              uuid        primary key default gen_random_uuid(),
    trip_id         uuid        not null references travel.travel_trip (id) on delete cascade,
    name            text        not null check (length(btrim(name)) between 1 and 60),
    position        integer     not null default 0,
    member_user_id  uuid,
    user_id         uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id        uuid,
    unique (trip_id, name)
);
comment on table travel.travel_traveller is 'arga:shared';

alter table travel.travel_expense
    add column if not exists amount numeric(12, 2) check (amount is null or amount >= 0),
    add column if not exists currency text check (currency is null or currency ~ '^[A-Z]{3}$'),
    add column if not exists fx_rate numeric(18, 8) check (fx_rate is null or fx_rate > 0),
    add column if not exists fx_on date,
    add column if not exists total_eur numeric(12, 2) check (total_eur is null or total_eur >= 0),
    add column if not exists spent_on date,
    add column if not exists paid_by uuid references travel.travel_traveller (id) on delete set null;

create table if not exists travel.travel_expense_share (
    id            uuid          primary key default gen_random_uuid(),
    trip_id       uuid          not null references travel.travel_trip (id) on delete cascade,
    expense_id    uuid          not null references travel.travel_expense (id) on delete cascade,
    traveller_id  uuid          not null references travel.travel_traveller (id) on delete cascade,
    amount        numeric(12, 2) not null check (amount >= 0),
    user_id       uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id      uuid,
    unique (expense_id, traveller_id)
);
comment on table travel.travel_expense_share is 'arga:shared';

create table if not exists travel.travel_settlement (
    id              uuid          primary key default gen_random_uuid(),
    trip_id         uuid          not null references travel.travel_trip (id) on delete cascade,
    from_traveller  uuid          not null references travel.travel_traveller (id) on delete cascade,
    to_traveller    uuid          not null references travel.travel_traveller (id) on delete cascade,
    amount_eur      numeric(12, 2) not null check (amount_eur > 0),
    settled_on      date          not null default current_date,
    note            text          check (note is null or length(note) <= 300),
    created_at      timestamptz   not null default now(),
    user_id         uuid          not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id        uuid,
    check (from_traveller <> to_traveller)
);
comment on table travel.travel_settlement is 'arga:shared';

create table if not exists travel.travel_note (
    id          uuid        primary key default gen_random_uuid(),
    trip_id     uuid        not null references travel.travel_trip (id) on delete cascade,
    category    text        not null default 'general'
                            check (category in ('general', 'visa', 'culture', 'tips', 'health',
                                                'other')),
    title       text        not null check (length(btrim(title)) between 1 and 120),
    body        text        not null default '' check (length(body) <= 20000),
    position    integer     not null default 0,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id    uuid
);
comment on table travel.travel_note is 'arga:shared';

create table if not exists travel.travel_check_item (
    id          uuid        primary key default gen_random_uuid(),
    trip_id     uuid        not null references travel.travel_trip (id) on delete cascade,
    list        text        not null default 'packing' check (list in ('packing', 'todo')),
    text        text        not null check (length(btrim(text)) between 1 and 200),
    position    integer     not null default 0,
    checked_at  timestamptz,
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id    uuid
);
comment on table travel.travel_check_item is 'arga:shared';

create table if not exists travel.travel_document (
    id            uuid        primary key default gen_random_uuid(),
    trip_id       uuid        not null references travel.travel_trip (id) on delete cascade,
    stay_id       uuid        references travel.travel_stay (id) on delete set null,
    leg_id        uuid        references travel.travel_leg (id) on delete set null,
    block_id      uuid        references travel.travel_block (id) on delete set null,
    name          text        not null check (length(btrim(name)) between 1 and 200),
    content_type  text        not null check (length(content_type) between 3 and 120),
    size          integer     not null check (size between 1 and 20971520),
    content       bytea       not null,
    created_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id      uuid,
    constraint travel_document_size_is_content check (size = octet_length(content)),
    constraint travel_document_one_link check (num_nonnulls(stay_id, leg_id, block_id) <= 1)
);
comment on table travel.travel_document is 'arga:shared';

create index if not exists travel_document_by_trip on travel.travel_document (trip_id, created_at);

alter table travel.travel_check_item
    add column if not exists traveller_id uuid
        references travel.travel_traveller (id) on delete set null;

create table if not exists travel.travel_day (
    id          uuid        primary key default gen_random_uuid(),
    trip_id     uuid        not null references travel.travel_trip (id) on delete cascade,
    day         date        not null,
    title       text        not null check (length(btrim(title)) between 1 and 80),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id    uuid,
    unique (trip_id, day) deferrable initially immediate
);
comment on table travel.travel_day is 'arga:shared';

alter table travel.travel_place
    add column if not exists category text
        check (category is null or category in (
            'restaurant', 'nightlife', 'cafe', 'market', 'beach', 'nature', 'viewpoint',
            'culture', 'castle', 'town', 'shopping', 'parking', 'lodging', 'other'));

alter table travel.travel_leg
    add column if not exists ticket_leg_id uuid
        references travel.travel_leg (id) on delete set null;

alter table travel.travel_leg drop constraint if exists travel_leg_number_check;
alter table travel.travel_leg add constraint travel_leg_number_check
    check (number is null or length(number) <= 40);
alter table travel.travel_leg drop constraint if exists travel_leg_from_code_check;
alter table travel.travel_leg add constraint travel_leg_from_code_check
    check (from_code is null or length(from_code) <= 40);
alter table travel.travel_leg drop constraint if exists travel_leg_to_code_check;
alter table travel.travel_leg add constraint travel_leg_to_code_check
    check (to_code is null or length(to_code) <= 40);
alter table travel.travel_leg drop constraint if exists travel_leg_terminal_check;
alter table travel.travel_leg add constraint travel_leg_terminal_check
    check (terminal is null or length(terminal) <= 40);
alter table travel.travel_leg drop constraint if exists travel_leg_seat_check;
alter table travel.travel_leg add constraint travel_leg_seat_check
    check (seat is null or length(seat) <= 80);

alter table travel.travel_trip
    add column if not exists summary text check (summary is null or length(summary) <= 1000),
    add column if not exists cover_looked_at timestamptz;

create table if not exists travel.travel_cover (
    trip_id         uuid        primary key references travel.travel_trip (id) on delete cascade,
    content         bytea       not null check (octet_length(content) <= 2 * 1024 * 1024),
    content_type    text        not null,
    thumb           bytea       not null,
    credit_author   text,
    credit_license  text,
    credit_page     text,
    updated_at      timestamptz not null default clock_timestamp(),
    user_id         uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    space_id        uuid
);
comment on table travel.travel_cover is 'arga:shared';

create index if not exists travel_block_place_id_idx on travel.travel_block (place_id);
create index if not exists travel_block_user_id_idx on travel.travel_block (user_id);
create index if not exists travel_check_item_traveller_id_idx on travel.travel_check_item (traveller_id);
create index if not exists travel_check_item_trip_id_idx on travel.travel_check_item (trip_id);
create index if not exists travel_check_item_user_id_idx on travel.travel_check_item (user_id);
create index if not exists travel_cover_user_id_idx on travel.travel_cover (user_id);
create index if not exists travel_day_user_id_idx on travel.travel_day (user_id);
create index if not exists travel_document_block_id_idx on travel.travel_document (block_id);
create index if not exists travel_document_leg_id_idx on travel.travel_document (leg_id);
create index if not exists travel_document_stay_id_idx on travel.travel_document (stay_id);
create index if not exists travel_document_user_id_idx on travel.travel_document (user_id);
create index if not exists travel_expense_paid_by_idx on travel.travel_expense (paid_by);
create index if not exists travel_expense_user_id_idx on travel.travel_expense (user_id);
create index if not exists travel_expense_share_traveller_id_idx on travel.travel_expense_share (traveller_id);
create index if not exists travel_expense_share_trip_id_idx on travel.travel_expense_share (trip_id);
create index if not exists travel_expense_share_user_id_idx on travel.travel_expense_share (user_id);
create index if not exists travel_home_place_id_idx on travel.travel_home (place_id);
create index if not exists travel_idea_user_id_idx on travel.travel_idea (user_id);
create index if not exists travel_idea_place_place_id_idx on travel.travel_idea_place (place_id);
create index if not exists travel_idea_place_user_id_idx on travel.travel_idea_place (user_id);
create index if not exists travel_leg_from_place_id_idx on travel.travel_leg (from_place_id);
create index if not exists travel_leg_ticket_leg_id_idx on travel.travel_leg (ticket_leg_id);
create index if not exists travel_leg_to_place_id_idx on travel.travel_leg (to_place_id);
create index if not exists travel_leg_user_id_idx on travel.travel_leg (user_id);
create index if not exists travel_note_trip_id_idx on travel.travel_note (trip_id);
create index if not exists travel_note_user_id_idx on travel.travel_note (user_id);
create index if not exists travel_other_place_place_id_idx on travel.travel_other_place (place_id);
create index if not exists travel_settlement_from_traveller_idx on travel.travel_settlement (from_traveller);
create index if not exists travel_settlement_to_traveller_idx on travel.travel_settlement (to_traveller);
create index if not exists travel_settlement_trip_id_idx on travel.travel_settlement (trip_id);
create index if not exists travel_settlement_user_id_idx on travel.travel_settlement (user_id);
create index if not exists travel_stay_place_id_idx on travel.travel_stay (place_id);
create index if not exists travel_stay_user_id_idx on travel.travel_stay (user_id);
create index if not exists travel_traveller_user_id_idx on travel.travel_traveller (user_id);
create index if not exists travel_trip_idea_id_idx on travel.travel_trip (idea_id);
create index if not exists travel_trip_user_id_idx on travel.travel_trip (user_id);
create index if not exists travel_visit_place_id_idx on travel.travel_visit (place_id);
create index if not exists travel_visit_stay_id_idx on travel.travel_visit (stay_id);
create index if not exists travel_visit_user_id_idx on travel.travel_visit (user_id);

alter table travel.travel_outbox
    add column if not exists key text generated always as (
        case type
            when 'travel.trip' then 'trip:' || (payload->>'trip_id')
            when 'travel.leg' then 'leg:' || (payload->>'leg_id')
            when 'travel.block' then 'block:' || (payload->>'block_id')
            when 'travel.plan' then 'plan:' || (payload->>'plan_id')
            else case
                when payload ? 'record' then 'record:' || (payload->'record'->>'id')
                when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
                when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
            end
        end
    ) stored;

create index if not exists travel_outbox_key on travel.travel_outbox (user_id, type, key, id desc)
    where key is not null;

create function travel.travel_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('travel_outbox', '');
    return null;
end;
$$;

create trigger travel_outbox_notify after insert on travel.travel_outbox
    for each statement execute function travel.travel_outbox_notify();

create table if not exists travel.travel_journal (
    id          uuid        primary key default gen_random_uuid(),
    trip_id     uuid        not null references travel.travel_trip (id) on delete cascade,
    day         date        not null,
    body        text        not null check (length(btrim(body)) between 1 and 20000),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table travel.travel_journal is 'arga:person';

create unique index if not exists travel_journal_user_id_trip_id_day_key
    on travel.travel_journal (user_id, trip_id, day);
create index if not exists travel_journal_trip_id_idx on travel.travel_journal (trip_id);
