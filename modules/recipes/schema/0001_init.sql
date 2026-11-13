create table recipes.recipes_food_category (
    id        text        primary key check (id ~ '^[a-z][a-z_]*$'),
    name      text        not null check (length(btrim(name)) > 0),
    emoji     text        not null check (length(btrim(emoji)) > 0),
    position  smallint    not null check (position > 0),
    user_id   uuid        default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table recipes.recipes_food_category is 'arga:catalog';

insert into recipes.recipes_food_category (id, name, emoji, position, user_id) values
    ('vegetable', 'Vegetables',              '🥬',  1, null),
    ('fruit',     'Fruit',                   '🍎',  2, null),
    ('protein',   'Meat',                    '🥩',  3, null),
    ('fish',      'Fish and seafood',        '🐟',  4, null),
    ('dairy',     'Dairy and eggs',          '🧀',  5, null),
    ('grain',     'Grains, bread and pasta', '🌾',  6, null),
    ('legume',    'Pulses',                  '🫘',  7, null),
    ('fat',       'Fats and oils',           '🫒',  8, null),
    ('spice',     'Spices and seasonings',   '🌶️',  9, null),
    ('sweet',     'Sugars and sweets',       '🍯', 10, null),
    ('liquid',    'Stocks and drinks',       '🍷', 11, null),
    ('other',     'Other',                   '🧂', 12, null);

create table recipes.recipes_food (
    id             uuid    primary key default gen_random_uuid(),
    name           text    not null check (length(btrim(name)) > 0),
    source         text    not null check (source in ('usda', 'off', 'manual')),
    source_ref     text,
    category_id    text    not null references recipes.recipes_food_category (id),

    kcal_100g      numeric(7, 2) not null check (kcal_100g >= 0 and kcal_100g <= 900),
    protein_100g   numeric(6, 2) not null check (protein_100g >= 0 and protein_100g <= 100),
    fat_100g       numeric(6, 2) not null check (fat_100g >= 0 and fat_100g <= 100),
    carbs_100g     numeric(6, 2) not null check (carbs_100g >= 0 and carbs_100g <= 100),
    fiber_100g     numeric(6, 2) check (fiber_100g >= 0 and fiber_100g <= 100),
    salt_100g      numeric(6, 3) check (salt_100g >= 0 and salt_100g <= 100),

    density_g_ml    numeric(5, 3) check (density_g_ml > 0 and density_g_ml < 3),
    grams_per_unit  numeric(7, 2) check (grams_per_unit > 0),

    corrected      boolean not null default false,
    imported_at    timestamptz not null default now(),
    user_id        uuid    default nullif(current_setting('arga.user_id', true), '')::uuid,

    constraint recipes_food_once_per_source
        unique nulls not distinct (user_id, source, source_ref, name)
);
comment on table recipes.recipes_food is 'arga:catalog';

create index recipes_food_by_name on recipes.recipes_food (lower(name));
create index recipes_food_by_category on recipes.recipes_food (category_id);

create table recipes.recipes_tag (
    id       uuid primary key default gen_random_uuid(),
    name     text not null check (length(btrim(name)) > 0),
    emoji    text,
    user_id  uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table recipes.recipes_tag is 'arga:person';

create unique index recipes_tag_name_per_person
    on recipes.recipes_tag (user_id, lower(btrim(name)));

create table recipes.recipes_recipe (
    id          uuid primary key default gen_random_uuid(),
    name        text not null check (length(btrim(name)) > 0),
    servings    smallint not null check (servings between 1 and 50),
    created_at  timestamptz not null default now(),
    user_id     uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table recipes.recipes_recipe is 'arga:person';

create unique index recipes_recipe_name_per_person
    on recipes.recipes_recipe (user_id, lower(btrim(name)));

create table recipes.recipes_recipe_version (
    id          uuid primary key default gen_random_uuid(),
    recipe_id   uuid not null references recipes.recipes_recipe (id) on delete cascade,
    number      integer not null check (number > 0),
    source      text not null check (source in ('app', 'tool')),
    servings    smallint not null check (servings between 1 and 50),
    note        text,
    created_at  timestamptz not null default now(),
    sealed_at   timestamptz,
    user_id     uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (recipe_id, number)
);
comment on table recipes.recipes_recipe_version is 'arga:person';

create unique index recipes_version_one_draft on recipes.recipes_recipe_version (recipe_id)
    where sealed_at is null;

alter table recipes.recipes_recipe
    add column current_version_id uuid references recipes.recipes_recipe_version (id);

create table recipes.recipes_recipe_ingredient (
    id          uuid primary key default gen_random_uuid(),
    version_id  uuid not null references recipes.recipes_recipe_version (id) on delete cascade,
    position    smallint not null check (position > 0),
    food_id     uuid references recipes.recipes_food (id),
    unresolved_name text check (length(btrim(unresolved_name)) > 0),
    quantity    numeric(9, 2) not null check (quantity > 0),
    unit        text not null check (unit in ('g', 'ml', 'unit', 'tbsp', 'tsp', 'pinch')),
    note        text,
    optional    boolean not null default false,
    user_id     uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (version_id, position),
    constraint recipes_ingredient_food_or_name
        check ((food_id is null) <> (unresolved_name is null))
);
comment on table recipes.recipes_recipe_ingredient is 'arga:person';

create index recipes_ingredient_by_version
    on recipes.recipes_recipe_ingredient (version_id, position);
create index recipes_ingredient_by_food on recipes.recipes_recipe_ingredient (food_id);

create table recipes.recipes_recipe_tag (
    recipe_id  uuid not null references recipes.recipes_recipe (id) on delete cascade,
    tag_id     uuid not null references recipes.recipes_tag (id) on delete cascade,
    user_id    uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (recipe_id, tag_id)
);
comment on table recipes.recipes_recipe_tag is 'arga:person';

create function recipes.recipes_refuse_sealed() returns trigger
language plpgsql as $$
declare
    version_id uuid;
begin
    if tg_table_name = 'recipes_recipe_version' then
        -- Deleting the whole recipe takes its versions with it, and that is allowed: it is the
        -- only way to lose a recipe, and it is explicit. When the cascade gets here the recipe is
        -- already gone, which tells it apart from deleting a single version, which would lose
        -- history nobody asked to lose.
        if tg_op = 'DELETE' and not exists (
            select 1 from recipes.recipes_recipe where id = old.recipe_id
        ) then
            return old;
        end if;
        -- Sealing is the only write allowed on a version: from draft to sealed.
        if old.sealed_at is not null then
            raise exception 'version % of the recipe is sealed and cannot change', old.number
                using errcode = 'check_violation';
        end if;
        if tg_op = 'DELETE' then
            return old;
        end if;
        return new;
    end if;

    -- The same for its ingredients: if the version is gone, the row goes with it.
    if tg_op = 'DELETE' and not exists (
        select 1 from recipes.recipes_recipe_version where id = old.version_id
    ) then
        return old;
    end if;

    -- The version the row hangs from, before and after the change: both must be drafts.
    for version_id in
        select v from unnest(array[
            case when tg_op <> 'INSERT' then (to_jsonb(old) ->> 'version_id')::uuid end,
            case when tg_op <> 'DELETE' then (to_jsonb(new) ->> 'version_id')::uuid end
        ]) as v
        where v is not null
    loop
        if exists (
            select 1 from recipes.recipes_recipe_version
            where id = version_id and sealed_at is not null
        ) then
            raise exception 'the recipe version is sealed and cannot change'
                using errcode = 'check_violation';
        end if;
    end loop;

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

create trigger recipes_version_immutable
    before update or delete on recipes.recipes_recipe_version
    for each row execute function recipes.recipes_refuse_sealed();

create trigger recipes_ingredient_immutable
    before insert or update or delete on recipes.recipes_recipe_ingredient
    for each row execute function recipes.recipes_refuse_sealed();

create table recipes.recipes_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'recipes.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table recipes.recipes_outbox is 'arga:person';

create index recipes_outbox_pending on recipes.recipes_outbox (id)
    where published_at is null;

create table recipes.recipes_step (
    id          uuid primary key default gen_random_uuid(),
    version_id  uuid not null references recipes.recipes_recipe_version (id) on delete cascade,
    position    smallint not null check (position > 0),

    action      text not null check (action in (
                    'wash', 'peel', 'chop', 'mix', 'knead', 'season', 'coat',
                    'fry', 'saute', 'boil', 'simmer', 'steam', 'bake', 'roast', 'grill',
                    'rest', 'marinate', 'chill', 'freeze', 'prove', 'blend', 'strain',
                    'assemble', 'serve'
                )),
    text        text not null check (length(btrim(text)) > 0 and length(text) <= 200),
    minutes     smallint not null check (minutes > 0 and minutes <= 2880),

    attended    boolean not null default true,

    equipment   text not null default 'none' check (equipment in (
                    'hob', 'oven', 'board', 'bowl', 'fridge', 'none'
                )),
    user_id     uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (version_id, position)
);
comment on table recipes.recipes_step is 'arga:person';

create index recipes_step_by_version on recipes.recipes_step (version_id, position);

create table recipes.recipes_step_dependency (
    version_id     uuid not null references recipes.recipes_recipe_version (id) on delete cascade,
    step_position  smallint not null check (step_position > 0),
    after_position smallint not null check (after_position > 0),
    user_id        uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (version_id, step_position, after_position),
    constraint recipes_dependency_points_backwards check (after_position < step_position)
);
comment on table recipes.recipes_step_dependency is 'arga:person';

create table recipes.recipes_step_ingredient (
    version_id      uuid not null references recipes.recipes_recipe_version (id) on delete cascade,
    step_position   smallint not null check (step_position > 0),
    ingredient_id   uuid not null references recipes.recipes_recipe_ingredient (id) on delete cascade,
    user_id         uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (version_id, step_position, ingredient_id)
);
comment on table recipes.recipes_step_ingredient is 'arga:person';

create trigger recipes_step_immutable
    before insert or update or delete on recipes.recipes_step
    for each row execute function recipes.recipes_refuse_sealed();

create trigger recipes_step_dependency_immutable
    before insert or update or delete on recipes.recipes_step_dependency
    for each row execute function recipes.recipes_refuse_sealed();

create trigger recipes_step_ingredient_immutable
    before insert or update or delete on recipes.recipes_step_ingredient
    for each row execute function recipes.recipes_refuse_sealed();

alter table recipes.recipes_recipe_version
    add column if not exists total_minutes smallint check (total_minutes >= 0),
    add column if not exists active_minutes smallint check (active_minutes >= 0);

create index recipes_version_by_total
    on recipes.recipes_recipe_version (total_minutes)
    where sealed_at is not null;

alter table recipes.recipes_food
    add column if not exists alias text
        check (alias is null or (length(btrim(alias)) > 0 and length(alias) <= 60));

create unique index if not exists recipes_food_alias_per_person
    on recipes.recipes_food (user_id, lower(btrim(alias)))
    where alias is not null;

alter table recipes.recipes_food
    add column if not exists nutrients jsonb
        check (nutrients is null or jsonb_typeof(nutrients) = 'object');

alter table recipes.recipes_food
    add column if not exists nutrients_checked_at timestamptz;

alter table recipes.recipes_food add column if not exists space_id uuid;
alter table recipes.recipes_recipe add column if not exists space_id uuid;
alter table recipes.recipes_recipe_version add column if not exists space_id uuid;
alter table recipes.recipes_recipe_ingredient add column if not exists space_id uuid;
alter table recipes.recipes_step add column if not exists space_id uuid;
alter table recipes.recipes_step_dependency add column if not exists space_id uuid;
alter table recipes.recipes_step_ingredient add column if not exists space_id uuid;

comment on table recipes.recipes_recipe is 'arga:shared';
comment on table recipes.recipes_recipe_version is 'arga:shared';
comment on table recipes.recipes_recipe_ingredient is 'arga:shared';
comment on table recipes.recipes_step is 'arga:shared';
comment on table recipes.recipes_step_dependency is 'arga:shared';
comment on table recipes.recipes_step_ingredient is 'arga:shared';

create or replace function recipes.recipes_refuse_sealed() returns trigger
language plpgsql as $$
declare
    version_id uuid;
begin
    -- Who owns it and which space it is in are not its content: sharing and unsharing change
    -- them on sealed versions too (ADR-0121).
    if tg_op = 'UPDATE'
       and (to_jsonb(new) - 'space_id' - 'user_id') = (to_jsonb(old) - 'space_id' - 'user_id') then
        return new;
    end if;

    if tg_table_name = 'recipes_recipe_version' then
        if tg_op = 'DELETE' and not exists (
            select 1 from recipes.recipes_recipe where id = old.recipe_id
        ) then
            return old;
        end if;
        if old.sealed_at is not null then
            raise exception 'version % of the recipe is sealed and cannot change', old.number
                using errcode = 'check_violation';
        end if;
        if tg_op = 'DELETE' then
            return old;
        end if;
        return new;
    end if;

    if tg_op = 'DELETE' and not exists (
        select 1 from recipes.recipes_recipe_version where id = old.version_id
    ) then
        return old;
    end if;

    for version_id in
        select v from unnest(array[
            case when tg_op <> 'INSERT' then (to_jsonb(old) ->> 'version_id')::uuid end,
            case when tg_op <> 'DELETE' then (to_jsonb(new) ->> 'version_id')::uuid end
        ]) as v
        where v is not null
    loop
        if exists (
            select 1 from recipes.recipes_recipe_version
            where id = version_id and sealed_at is not null
        ) then
            raise exception 'the recipe version is sealed and cannot change'
                using errcode = 'check_violation';
        end if;
    end loop;

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

alter table recipes.recipes_step drop constraint if exists recipes_step_action_check;
alter table recipes.recipes_step
    add constraint recipes_step_action_check check (action in (
        'wash', 'peel', 'chop', 'mix', 'knead', 'season', 'coat',
        'fry', 'saute', 'boil', 'simmer', 'steam', 'bake', 'roast', 'grill', 'toast',
        'rest', 'marinate', 'chill', 'freeze', 'prove', 'blend', 'strain',
        'assemble', 'serve'
    ));

alter table recipes.recipes_step drop constraint if exists recipes_step_equipment_check;
alter table recipes.recipes_step
    add constraint recipes_step_equipment_check check (equipment in (
        'hob', 'oven', 'air_fryer', 'board', 'bowl', 'fridge', 'none'
    ));

alter table recipes.recipes_food drop constraint if exists recipes_food_kcal_100g_check;
alter table recipes.recipes_food
    add constraint recipes_food_kcal_100g_check check (kcal_100g >= 0 and kcal_100g <= 1000);

alter table recipes.recipes_food
    add column if not exists provenance text
        check (provenance is null or (length(btrim(provenance)) > 0 and length(provenance) <= 120)),
    add column if not exists micros_from uuid
        references recipes.recipes_food (id) on delete set null,
    add column if not exists edible_fraction numeric(4, 3)
        check (edible_fraction is null or (edible_fraction > 0 and edible_fraction <= 1));

alter table recipes.recipes_food
    add constraint recipes_food_micros_not_itself check (micros_from is null or micros_from <> id);

create table recipes.recipes_food_portion (
    id        uuid primary key default gen_random_uuid(),
    food_id   uuid not null references recipes.recipes_food (id) on delete cascade,
    name      text not null check (length(btrim(name)) > 0 and length(name) <= 40),
    grams     numeric(8, 2) not null check (grams > 0 and grams <= 5000),
    user_id   uuid default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table recipes.recipes_food_portion is 'arga:catalog';

create unique index recipes_food_portion_name
    on recipes.recipes_food_portion (food_id, lower(btrim(name)));

alter table recipes.recipes_recipe_ingredient
    add column if not exists portion text
        check (portion is null or (length(btrim(portion)) > 0 and length(portion) <= 40)),
    add column if not exists as_purchased boolean not null default false;

alter table recipes.recipes_recipe_ingredient
    add constraint recipes_ingredient_portion_in_units check (portion is null or unit = 'unit');

alter table recipes.recipes_food_category no force row level security;
insert into recipes.recipes_food_category (id, name, emoji, position, user_id)
values ('supplement', 'Supplements', '💊', 13, null)
on conflict (id) do nothing;
alter table recipes.recipes_food_category force row level security;

alter table recipes.recipes_food
    add column if not exists nutrients_per text not null default '100g'
        check (nutrients_per in ('100g', 'unit')),
    add column if not exists unit_name text
        check (unit_name is null or (length(btrim(unit_name)) > 0 and length(unit_name) <= 30));

alter table recipes.recipes_food
    add constraint recipes_food_unit_named check (nutrients_per = '100g' or unit_name is not null);

alter table recipes.recipes_food
    add column if not exists replaced_by uuid
        references recipes.recipes_food (id) on delete set null,
    add column if not exists archived_at timestamptz;

alter table recipes.recipes_food
    add constraint recipes_food_not_replaced_by_itself
        check (replaced_by is null or replaced_by <> id);

create index if not exists recipes_food_micros_from_idx on recipes.recipes_food (micros_from);
create index if not exists recipes_food_replaced_by_idx on recipes.recipes_food (replaced_by);
create index if not exists recipes_food_category_user_id_idx on recipes.recipes_food_category (user_id);
create index if not exists recipes_food_portion_user_id_idx on recipes.recipes_food_portion (user_id);
create index if not exists recipes_recipe_current_version_id_idx on recipes.recipes_recipe (current_version_id);
create index if not exists recipes_recipe_ingredient_user_id_idx on recipes.recipes_recipe_ingredient (user_id);
create index if not exists recipes_recipe_tag_tag_id_idx on recipes.recipes_recipe_tag (tag_id);
create index if not exists recipes_recipe_tag_user_id_idx on recipes.recipes_recipe_tag (user_id);
create index if not exists recipes_recipe_version_user_id_idx on recipes.recipes_recipe_version (user_id);
create index if not exists recipes_step_user_id_idx on recipes.recipes_step (user_id);
create index if not exists recipes_step_dependency_user_id_idx on recipes.recipes_step_dependency (user_id);
create index if not exists recipes_step_ingredient_ingredient_id_idx on recipes.recipes_step_ingredient (ingredient_id);
create index if not exists recipes_step_ingredient_user_id_idx on recipes.recipes_step_ingredient (user_id);

alter table recipes.recipes_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists recipes_outbox_key on recipes.recipes_outbox (user_id, type, key, id desc)
    where key is not null;

create function recipes.fold(value text) returns text
language sql immutable parallel safe as $$
    select translate(lower(value), U&'\00e1\00e0\00e2\00e4\00e3\00e9\00e8\00ea\00eb\00ed\00ec\00ee\00ef\00f3\00f2\00f4\00f6\00f5\00fa\00f9\00fb\00fc\00f1\00e7', 'aaaaaeeeeiiiiooooouuuunc')
$$;

create function recipes.recipes_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('recipes_outbox', '');
    return null;
end;
$$;

create trigger recipes_outbox_notify after insert on recipes.recipes_outbox
    for each statement execute function recipes.recipes_outbox_notify();

alter table recipes.recipes_recipe add column if not exists archived_at timestamptz;
