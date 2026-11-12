create table training.training_gym (
    id          uuid        primary key default gen_random_uuid(),
    name        text        not null unique check (length(btrim(name)) > 0),
    active      boolean     not null default true,
    created_at  timestamptz not null default now()
);

create table training.training_muscle (
    id      text primary key,
    name    text not null,
    region  text not null check (region in ('upper', 'lower', 'core'))
);

insert into training.training_muscle (id, name, region) values
    ('chest', 'Pecho', 'upper'),
    ('front_delts', 'Deltoide anterior', 'upper'),
    ('side_delts', 'Deltoide lateral', 'upper'),
    ('rear_delts', 'Deltoide posterior', 'upper'),
    ('lats', 'Dorsal', 'upper'),
    ('upper_back', 'Espalda alta', 'upper'),
    ('biceps', 'Bíceps', 'upper'),
    ('triceps', 'Tríceps', 'upper'),
    ('forearms', 'Antebrazo', 'upper'),
    ('quads', 'Cuádriceps', 'lower'),
    ('hamstrings', 'Isquiotibiales', 'lower'),
    ('glutes', 'Glúteo', 'lower'),
    ('calves', 'Gemelo', 'lower'),
    ('adductors', 'Aductores', 'lower'),
    ('abs', 'Abdomen', 'core'),
    ('lower_back', 'Lumbar', 'core');

create table training.training_exercise (
    id                  uuid primary key default gen_random_uuid(),
    name                text not null unique check (length(btrim(name)) > 0),
    pattern             text not null check (pattern in (
                            'horizontal_push', 'vertical_push',
                            'horizontal_pull', 'vertical_pull',
                            'knee_dominant', 'hip_dominant',
                            'isolation'
                        )),
    load_type           text not null check (load_type in ('external', 'bodyweight', 'weighted_bodyweight')),
    bodyweight_factor   numeric(4, 3) check (bodyweight_factor > 0 and bodyweight_factor <= 1.5),
    unilateral          boolean not null default false,
    created_at          timestamptz not null default now(),
    constraint training_exercise_factor_only_with_bodyweight
        check ((load_type = 'external') = (bodyweight_factor is null))
);

create table training.training_exercise_muscle (
    exercise_id   uuid not null references training.training_exercise (id) on delete cascade,
    muscle_id     text not null references training.training_muscle (id),
    contribution  numeric(2, 1) not null check (contribution in (0.5, 1.0)),
    primary key (exercise_id, muscle_id)
);

create table training.training_variant (
    id              uuid primary key default gen_random_uuid(),
    exercise_id     uuid not null references training.training_exercise (id),
    name            text not null check (length(btrim(name)) > 0),
    implement       text not null check (implement in ('barbell', 'dumbbell', 'smith', 'machine', 'cable', 'bodyweight')),
    gym_id          uuid references training.training_gym (id),
    min_increment   numeric(5, 2) not null check (min_increment > 0),
    index_weight    smallint not null check (index_weight in (1, 2, 3)),
    active          boolean not null default true,
    created_at      timestamptz not null default now(),
    constraint training_variant_one_per_implement_and_gym
        unique nulls not distinct (exercise_id, implement, gym_id)
);

create index training_variant_exercise on training.training_variant (exercise_id);

create table training.training_plan (
    id          uuid primary key default gen_random_uuid(),
    name        text not null check (length(btrim(name)) > 0),
    active      boolean not null default false,
    created_at  timestamptz not null default now()
);

create unique index training_plan_one_active on training.training_plan (active) where active;

create table training.training_plan_version (
    id            uuid primary key default gen_random_uuid(),
    plan_id       uuid not null references training.training_plan (id),
    number        integer not null check (number > 0),
    valid_from    date,
    published_at  timestamptz,
    created_at    timestamptz not null default now(),
    unique (plan_id, number),
    constraint training_plan_version_published_has_date
        check ((published_at is null) = (valid_from is null))
);

create table training.training_plan_day (
    id               uuid primary key default gen_random_uuid(),
    plan_version_id  uuid not null references training.training_plan_version (id) on delete cascade,
    name             text not null check (length(btrim(name)) > 0),
    kind             text not null check (kind in ('push', 'pull', 'leg', 'full', 'other')),
    position         smallint not null check (position > 0),
    unique (plan_version_id, position)
);

create table training.training_plan_slot (
    id            uuid primary key default gen_random_uuid(),
    plan_day_id   uuid not null references training.training_plan_day (id) on delete cascade,
    position      smallint not null check (position > 0),
    target_sets   smallint not null check (target_sets between 1 and 20),
    rep_min       smallint not null check (rep_min between 1 and 100),
    rep_max       smallint not null check (rep_max between 1 and 100),
    progression   text not null default 'double_progression' check (progression in ('double_progression')),
    allow_both    boolean not null default false,
    unique (plan_day_id, position),
    constraint training_plan_slot_rep_range check (rep_min <= rep_max)
);

create table training.training_plan_slot_option (
    plan_slot_id  uuid not null references training.training_plan_slot (id) on delete cascade,
    variant_id    uuid not null references training.training_variant (id),
    priority      smallint not null check (priority > 0),
    primary key (plan_slot_id, variant_id),
    unique (plan_slot_id, priority)
);

create function training.training_version_of_day(day_id uuid) returns uuid
language sql stable as $$
    select plan_version_id from training.training_plan_day where id = day_id
$$;

create function training.training_version_of_slot(slot_id uuid) returns uuid
language sql stable as $$
    select d.plan_version_id
    from training.training_plan_slot s join training.training_plan_day d on d.id = s.plan_day_id
    where s.id = slot_id
$$;

create function training.training_version_of_row(table_name text, data jsonb) returns uuid
language sql stable as $$
    select case table_name
        when 'training_plan_day' then (data ->> 'plan_version_id')::uuid
        when 'training_plan_slot' then training.training_version_of_day((data ->> 'plan_day_id')::uuid)
        when 'training_plan_slot_option' then training.training_version_of_slot((data ->> 'plan_slot_id')::uuid)
    end
$$;

create function training.training_refuse_published() returns trigger
language plpgsql as $$
declare
    version_id uuid;
begin
    if tg_table_name = 'training_plan_version' then
        -- Publicar es la única escritura que se admite sobre una versión: de borrador a publicada.
        if old.published_at is not null then
            raise exception 'la versión % del plan está publicada y no se modifica', old.number
                using errcode = 'check_violation';
        end if;
        if tg_op = 'DELETE' then
            return old;
        end if;
        return new;
    end if;

    -- De qué versión cuelga la fila, antes o después del cambio: las dos tienen que ser borrador.
    for version_id in
        select v from unnest(array[
            case when tg_op <> 'INSERT' then training.training_version_of_row(tg_table_name, to_jsonb(old)) end,
            case when tg_op <> 'DELETE' then training.training_version_of_row(tg_table_name, to_jsonb(new)) end
        ]) as v
        where v is not null
    loop
        if exists (
            select 1 from training.training_plan_version
            where id = version_id and published_at is not null
        ) then
            raise exception 'la versión del plan está publicada y no se modifica'
                using errcode = 'check_violation';
        end if;
    end loop;

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

create trigger training_plan_version_immutable
    before update or delete on training.training_plan_version
    for each row execute function training.training_refuse_published();

create trigger training_plan_day_immutable
    before insert or update or delete on training.training_plan_day
    for each row execute function training.training_refuse_published();

create trigger training_plan_slot_immutable
    before insert or update or delete on training.training_plan_slot
    for each row execute function training.training_refuse_published();

create trigger training_plan_slot_option_immutable
    before insert or update or delete on training.training_plan_slot_option
    for each row execute function training.training_refuse_published();

create table training.training_settings (
    id                   boolean primary key default true check (id),
    weekly_goal          smallint not null default 5 check (weekly_goal between 1 and 14),
    unit                 text not null default 'kg' check (unit in ('kg')),
    default_increments   jsonb not null default '{"barbell": 2.5, "dumbbell": 2, "smith": 2.5, "machine": 5, "cable": 5, "bodyweight": 1}',
    updated_at           timestamptz not null default now()
);

insert into training.training_settings default values;

create table training.training_bodyweight (
    day  date primary key,
    kg   numeric(5, 2) not null check (kg > 20 and kg < 400)
);

alter table training.training_plan_day
    add constraint training_plan_day_version_and_id unique (plan_version_id, id);

create table training.training_rotation (
    id               uuid primary key default gen_random_uuid(),
    plan_version_id  uuid not null references training.training_plan_version (id),
    number           integer not null unique check (number > 0),
    status           text not null default 'open' check (status in ('open', 'complete', 'abandoned')),
    opened_at        timestamptz not null default now(),
    closed_at        timestamptz,
    unique (id, plan_version_id),
    constraint training_rotation_closed_has_date check ((status = 'open') = (closed_at is null))
);

create unique index training_rotation_one_open on training.training_rotation (status) where status = 'open';

create table training.training_session (
    id                uuid primary key default gen_random_uuid(),
    rotation_id       uuid not null,
    plan_version_id   uuid not null,
    plan_day_id       uuid not null,
    gym_id            uuid references training.training_gym (id),
    day               date not null,
    started_at        timestamptz not null,
    ended_at          timestamptz,
    duration_seconds  integer check (duration_seconds >= 0),
    notes             text,
    created_at        timestamptz not null default now(),
    foreign key (rotation_id, plan_version_id)
        references training.training_rotation (id, plan_version_id),
    foreign key (plan_version_id, plan_day_id)
        references training.training_plan_day (plan_version_id, id),
    constraint training_session_ends_after_start check (ended_at is null or ended_at >= started_at)
);

create unique index training_session_one_in_progress on training.training_session ((true))
    where ended_at is null;
create index training_session_day on training.training_session (day desc);
create index training_session_rotation on training.training_session (rotation_id);

create table training.training_session_exercise (
    id            uuid primary key default gen_random_uuid(),
    session_id    uuid not null references training.training_session (id) on delete cascade,
    plan_slot_id  uuid references training.training_plan_slot (id),
    variant_id    uuid not null references training.training_variant (id),
    position      smallint not null check (position > 0),
    created_at    timestamptz not null default now(),
    unique (session_id, plan_slot_id, variant_id),
    foreign key (plan_slot_id, variant_id)
        references training.training_plan_slot_option (plan_slot_id, variant_id)
);

create index training_session_exercise_session on training.training_session_exercise (session_id);
create index training_session_exercise_variant on training.training_session_exercise (variant_id);

create function training.training_one_variant_per_slot() returns trigger
language plpgsql as $$
begin
    if new.plan_slot_id is null then
        return new;
    end if;
    if exists (
        select 1
        from training.training_session_exercise other
        join training.training_plan_slot slot on slot.id = other.plan_slot_id
        where other.session_id = new.session_id
          and other.plan_slot_id = new.plan_slot_id
          and other.variant_id <> new.variant_id
          and other.id <> new.id
          and not slot.allow_both
    ) then
        raise exception 'este slot no permite dos variantes en la misma sesión'
            using errcode = 'check_violation';
    end if;
    return new;
end;
$$;

create trigger training_session_exercise_one_variant
    before insert or update on training.training_session_exercise
    for each row execute function training.training_one_variant_per_slot();

create table training.training_set_log (
    id                   uuid primary key default gen_random_uuid(),
    session_exercise_id  uuid not null references training.training_session_exercise (id) on delete cascade,
    number               smallint not null check (number between 1 and 50),
    reps                 smallint check (reps between 0 and 200),
    weight               numeric(6, 2) check (weight >= 0),
    added_load           numeric(6, 2) check (added_load >= 0),
    completed            boolean not null default true,
    confirmed_at         timestamptz not null,
    rir                  smallint check (rir between 0 and 10),
    revision             integer not null default 1 check (revision > 0),
    updated_at           timestamptz not null default now(),
    unique (session_exercise_id, number),
    constraint training_set_log_completed_has_reps check (not completed or reps is not null)
);

create index training_set_log_confirmed on training.training_set_log (confirmed_at);

create table training.training_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type ~ '^training\.[a-z_]+$'),
    ts            timestamptz not null,
    payload       jsonb not null,
    dedup_hash    text not null unique,
    created_at    timestamptz not null default now(),
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text
);

create index training_outbox_pending on training.training_outbox (id) where published_at is null;

alter table training.training_session_exercise
    add column notes text check (notes is null or length(notes) <= 2000);

alter table training.training_session
    add column source text not null default 'app' check (source in ('app', 'import'));

create table training.training_activity_type (
    id          uuid primary key default gen_random_uuid(),
    name        text not null check (length(btrim(name)) > 0 and length(name) <= 60),
    active      boolean not null default true,
    created_at  timestamptz not null default now()
);

create unique index training_activity_type_name on training.training_activity_type (lower(btrim(name)));

create table training.training_activity (
    id                uuid primary key default gen_random_uuid(),
    activity_type_id  uuid not null references training.training_activity_type (id),
    day               date not null,
    duration_seconds  integer check (duration_seconds >= 0 and duration_seconds <= 86400),
    notes             text check (notes is null or length(notes) <= 2000),
    source            text not null default 'app' check (source in ('app', 'import')),
    created_at        timestamptz not null default now()
);

create index training_activity_day on training.training_activity (day desc);

alter table training.training_session add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_session is 'arga:person';

alter table training.training_session_exercise add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_session_exercise is 'arga:person';

alter table training.training_set_log add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_set_log is 'arga:person';

alter table training.training_outbox add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_outbox is 'arga:person';

alter table training.training_plan add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_plan is 'arga:person';

alter table training.training_plan_version add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_plan_version is 'arga:person';

alter table training.training_plan_day add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_plan_day is 'arga:person';

alter table training.training_plan_slot add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_plan_slot is 'arga:person';

alter table training.training_plan_slot_option add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_plan_slot_option is 'arga:person';

alter table training.training_settings add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_settings is 'arga:person';

alter table training.training_bodyweight add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_bodyweight is 'arga:person';

alter table training.training_activity add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_activity is 'arga:person';

alter table training.training_rotation add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_rotation is 'arga:person';

alter table training.training_gym add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_gym is 'arga:catalog';

alter table training.training_muscle add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_muscle is 'arga:catalog';

alter table training.training_exercise add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_exercise is 'arga:catalog';

alter table training.training_exercise_muscle add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_exercise_muscle is 'arga:catalog';

alter table training.training_variant add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_variant is 'arga:catalog';

alter table training.training_activity_type add column if not exists user_id uuid
    default nullif(current_setting('arga.user_id', true), '')::uuid;
comment on table training.training_activity_type is 'arga:catalog';

update training.training_muscle set user_id = null;
comment on table training.training_muscle is 'arga:system';

delete from training.training_settings where user_id is null;

alter table training.training_session alter column user_id set not null;
alter table training.training_session_exercise alter column user_id set not null;
alter table training.training_set_log alter column user_id set not null;
alter table training.training_outbox alter column user_id set not null;
alter table training.training_plan alter column user_id set not null;
alter table training.training_plan_version alter column user_id set not null;
alter table training.training_plan_day alter column user_id set not null;
alter table training.training_plan_slot alter column user_id set not null;
alter table training.training_plan_slot_option alter column user_id set not null;
alter table training.training_settings alter column user_id set not null;
alter table training.training_bodyweight alter column user_id set not null;
alter table training.training_activity alter column user_id set not null;
alter table training.training_rotation alter column user_id set not null;

create unique index training_settings_per_person on training.training_settings (user_id);
create unique index training_bodyweight_per_person on training.training_bodyweight (user_id, day);
create unique index training_rotation_number_per_person on training.training_rotation (user_id, number);
create unique index training_rotation_one_open_per_person on training.training_rotation (user_id)
    where status = 'open';
create unique index training_session_one_in_progress_per_person on training.training_session (user_id)
    where ended_at is null;
create unique index training_plan_one_active_per_person on training.training_plan (user_id) where active;
create unique index training_outbox_per_person on training.training_outbox (user_id, dedup_hash);
create unique index training_gym_name_per_person on training.training_gym (user_id, name);
create unique index training_exercise_name_per_person on training.training_exercise (user_id, name);
create unique index training_activity_type_name_per_person
    on training.training_activity_type (user_id, lower(btrim(name)));

alter table training.training_settings drop constraint training_settings_pkey;
alter table training.training_settings add constraint training_settings_per_person
    primary key using index training_settings_per_person;

alter table training.training_bodyweight drop constraint training_bodyweight_pkey;
alter table training.training_bodyweight add constraint training_bodyweight_per_person
    primary key using index training_bodyweight_per_person;

alter table training.training_rotation drop constraint training_rotation_number_key;
drop index training.training_rotation_one_open;
drop index training.training_session_one_in_progress;
drop index training.training_plan_one_active;
alter table training.training_outbox drop constraint training_outbox_dedup_hash_key;
alter table training.training_gym drop constraint training_gym_name_key;
alter table training.training_exercise drop constraint training_exercise_name_key;
drop index training.training_activity_type_name;

alter table training.training_exercise_muscle no force row level security;

with ranked as (
    select exercise_id, muscle_id,
           row_number() over (
               partition by exercise_id
               order by array_position(array[
                   'chest', 'upper_back', 'lats', 'quads', 'hamstrings', 'glutes',
                   'front_delts', 'side_delts', 'rear_delts', 'biceps', 'triceps',
                   'calves', 'adductors', 'abs', 'forearms', 'lower_back'
               ], muscle_id) nulls last, muscle_id
           ) as rank
    from training.training_exercise_muscle
    where contribution = 1.0
)
update training.training_exercise_muscle em
set contribution = 0.5
from ranked
where ranked.exercise_id = em.exercise_id
  and ranked.muscle_id = em.muscle_id
  and ranked.rank > 1;

alter table training.training_exercise_muscle force row level security;

create unique index training_exercise_one_primary
    on training.training_exercise_muscle (exercise_id) where contribution = 1.0;

create table training.training_point_review (
    id                   uuid primary key default gen_random_uuid(),
    user_id              uuid not null
                         default nullif(current_setting('arga.user_id', true), '')::uuid,
    session_exercise_id  uuid not null
                         references training.training_session_exercise (id) on delete cascade,
    verdict              text not null check (verdict in ('counted', 'excluded')),
    created_at           timestamptz not null default now(),
    unique (user_id, session_exercise_id)
);

comment on table training.training_point_review is 'arga:person';

create table training.training_series_mark (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    variant_id  uuid not null references training.training_variant (id),
    gym_id      uuid references training.training_gym (id),
    day         date not null,
    kind        text not null check (kind in ('split', 'join')),
    created_at  timestamptz not null default now(),
    constraint training_series_mark_one_per_day unique nulls not distinct (user_id, variant_id, gym_id, day)
);

comment on table training.training_series_mark is 'arga:person';

alter table training.training_activity add column start_time time not null default '06:30';

alter table training.training_activity
    drop constraint training_activity_source_check,
    add constraint training_activity_source_check check (source in ('app', 'import', 'received'));

create table training.training_activity_received (
    origin_id    text        not null check (length(origin_id) between 1 and 200),
    received_at  timestamptz not null default now(),
    user_id      uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    primary key (user_id, origin_id)
);
comment on table training.training_activity_received is 'arga:person';

alter table training.training_activity alter column start_time set default '18:30';

update training.training_activity
set start_time = '18:30'
where start_time = '06:30' and source in ('app', 'import') and created_at < '2026-09-29';

alter table training.training_activity no force row level security;

update training.training_activity
set start_time = '18:30'
where start_time = '06:30' and source in ('app', 'import') and created_at < '2026-09-29';

alter table training.training_activity force row level security;

alter table training.training_activity add column band_id text check (band_id is null or length(band_id) <= 200);
alter table training.training_activity add column band jsonb;
alter table training.training_activity add column ongoing boolean not null default false;

create unique index training_activity_band on training.training_activity (user_id, band_id)
    where band_id is not null;

alter table training.training_activity_type add column band_kinds text[] not null default '{}';

alter table training.training_session add column band_id text check (band_id is null or length(band_id) <= 200);

create index if not exists training_activity_activity_type_id_idx on training.training_activity (activity_type_id);
create index if not exists training_exercise_muscle_muscle_id_idx on training.training_exercise_muscle (muscle_id);
create index if not exists training_exercise_muscle_user_id_idx on training.training_exercise_muscle (user_id);
create index if not exists training_muscle_user_id_idx on training.training_muscle (user_id);
create index if not exists training_plan_day_user_id_idx on training.training_plan_day (user_id);
create index if not exists training_plan_slot_user_id_idx on training.training_plan_slot (user_id);
create index if not exists training_plan_slot_option_user_id_idx on training.training_plan_slot_option (user_id);
create index if not exists training_plan_slot_option_variant_id_idx on training.training_plan_slot_option (variant_id);
create index if not exists training_plan_version_user_id_idx on training.training_plan_version (user_id);
create index if not exists training_point_review_session_exercise_id_idx on training.training_point_review (session_exercise_id);
create index if not exists training_rotation_plan_version_id_idx on training.training_rotation (plan_version_id);
create index if not exists training_series_mark_gym_id_idx on training.training_series_mark (gym_id);
create index if not exists training_series_mark_variant_id_idx on training.training_series_mark (variant_id);
create index if not exists training_session_gym_id_idx on training.training_session (gym_id);
create index if not exists training_session_plan_version_id_plan_day_id_idx on training.training_session (plan_version_id, plan_day_id);
create index if not exists training_session_rotation_id_plan_version_id_idx on training.training_session (rotation_id, plan_version_id);
create index if not exists training_session_exercise_plan_slot_id_idx on training.training_session_exercise (plan_slot_id);
create index if not exists training_session_exercise_plan_slot_id_variant_id_idx on training.training_session_exercise (plan_slot_id, variant_id);
create index if not exists training_session_exercise_user_id_idx on training.training_session_exercise (user_id);
create index if not exists training_set_log_user_id_idx on training.training_set_log (user_id);
create index if not exists training_variant_gym_id_idx on training.training_variant (gym_id);
create index if not exists training_variant_user_id_idx on training.training_variant (user_id);

alter table training.training_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists training_outbox_key on training.training_outbox (user_id, type, key, id desc)
    where key is not null;
