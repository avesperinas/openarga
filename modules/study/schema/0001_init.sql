create table study.study_attachment (
    id            uuid        primary key default gen_random_uuid(),
    filename      text        not null check (length(btrim(filename)) between 1 and 200),
    content_type  text        not null check (length(content_type) between 3 and 120),
    size          integer     not null check (size between 1 and 20971520),
    content       bytea       not null,
    created_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint study_attachment_size_is_content check (size = octet_length(content))
);
comment on table study.study_attachment is 'arga:person';

create table study.study_course (
    id            uuid        primary key default gen_random_uuid(),
    name          text        not null check (length(btrim(name)) between 1 and 200),
    kind          text        not null default 'course'
                              check (kind in ('master', 'degree', 'course', 'certification',
                                              'language', 'other')),
    institution   text        check (institution is null or length(btrim(institution)) between 1 and 200),
    modality      text        not null default 'in_person'
                              check (modality in ('in_person', 'online', 'hybrid')),
    starts_on     date,
    ends_on       date,
    status        text        not null default 'active'
                              check (status in ('planned', 'active', 'finished', 'abandoned')),
    credits       numeric(6, 2) check (credits is null or credits > 0),
    hours         numeric(7, 2) check (hours is null or hours > 0),
    scale_max     numeric(5, 2) not null default 10 check (scale_max in (10, 100)),
    pass_mark     numeric(5, 2) not null default 5,
    target_grade  numeric(5, 2),
    final_grade   numeric(5, 2),
    tone          smallint    not null default 1 check (tone between 1 and 10),
    campus_url    text        check (campus_url is null or campus_url ~ '^https?://[^\s]+$'),
    tz            text        not null default 'Europe/Madrid' check (length(tz) between 3 and 64),
    note          text        check (note is null or length(btrim(note)) between 1 and 4000),
    closed_on     date,
    certificate_id uuid       references study.study_attachment (id) on delete set null,
    source        text        not null default 'app' check (source in ('app', 'tool')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint study_course_in_order check (ends_on is null or starts_on is null or ends_on >= starts_on),
    constraint study_course_pass_on_scale check (pass_mark > 0 and pass_mark <= scale_max),
    constraint study_course_target_on_scale
        check (target_grade is null or (target_grade > 0 and target_grade <= scale_max)),
    constraint study_course_final_on_scale
        check (final_grade is null or (final_grade >= 0 and final_grade <= scale_max)),
    constraint study_course_closed_has_date
        check ((status in ('finished', 'abandoned')) = (closed_on is not null))
);
comment on table study.study_course is 'arga:person';

create index study_course_by_status on study.study_course (status);

create table study.study_subject (
    id            uuid        primary key default gen_random_uuid(),
    course_id     uuid        not null references study.study_course (id) on delete cascade,
    name          text        not null check (length(btrim(name)) between 1 and 200),
    teacher       text        check (teacher is null or length(btrim(teacher)) between 1 and 200),
    credits       numeric(5, 2) check (credits is null or credits > 0),
    period        text        check (period is null or length(btrim(period)) between 1 and 60),
    final_grade   numeric(5, 2) check (final_grade is null or final_grade >= 0),
    position      smallint    not null default 0,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table study.study_subject is 'arga:person';

create index study_subject_by_course on study.study_subject (course_id, position);

create table study.study_schedule (
    id            uuid        primary key default gen_random_uuid(),
    course_id     uuid        not null references study.study_course (id) on delete cascade,
    subject_id    uuid        references study.study_subject (id) on delete cascade,
    rrule         text        not null check (rrule like 'FREQ=%'),
    starts_on     date        not null,
    start_time    time        not null,
    end_time      time        not null,
    place         text        check (place is null or length(btrim(place)) between 1 and 200),
    url           text        check (url is null or url ~ '^https?://[^\s]+$'),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint study_schedule_in_order check (end_time > start_time)
);
comment on table study.study_schedule is 'arga:person';

create index study_schedule_by_course on study.study_schedule (course_id);

create table study.study_session (
    id            uuid        primary key default gen_random_uuid(),
    course_id     uuid        not null references study.study_course (id) on delete cascade,
    subject_id    uuid        references study.study_subject (id) on delete cascade,
    schedule_id   uuid        references study.study_schedule (id) on delete set null,
    original_start timestamptz,
    kind          text        not null default 'class' check (kind in ('class', 'tutorial', 'event')),
    title         text        check (title is null or length(btrim(title)) between 1 and 200),
    starts_at     timestamptz not null,
    ends_at       timestamptz not null,
    place         text        check (place is null or length(btrim(place)) between 1 and 200),
    url           text        check (url is null or url ~ '^https?://[^\s]+$'),
    status        text        not null default 'scheduled' check (status in ('scheduled', 'cancelled')),
    attendance    text        check (attendance in ('present', 'absent')),
    topic         text        check (topic is null or length(btrim(topic)) between 1 and 300),
    touched       boolean     not null default false,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint study_session_in_order check (ends_at > starts_at),
    constraint study_session_generated_has_origin
        check (schedule_id is null or original_start is not null),
    constraint study_session_loose_has_title check (kind = 'class' or title is not null)
);
comment on table study.study_session is 'arga:person';

create index study_session_by_start on study.study_session (starts_at);
create index study_session_by_course on study.study_session (course_id, starts_at);
create unique index study_session_once_per_occurrence
    on study.study_session (schedule_id, original_start) where schedule_id is not null;

create table study.study_assessment (
    id            uuid        primary key default gen_random_uuid(),
    course_id     uuid        not null references study.study_course (id) on delete cascade,
    subject_id    uuid        references study.study_subject (id) on delete cascade,
    title         text        not null check (length(btrim(title)) between 1 and 200),
    kind          text        not null default 'assignment'
                              check (kind in ('assignment', 'exam', 'practical', 'participation',
                                              'other')),
    due_on        date,
    due_time      time,
    weight        numeric(5, 2) check (weight is null or (weight > 0 and weight <= 100)),
    min_grade     numeric(5, 2) check (min_grade is null or min_grade >= 0),
    status        text        not null default 'pending'
                              check (status in ('pending', 'submitted', 'graded')),
    grade         numeric(5, 2) check (grade is null or grade >= 0),
    note          text        check (note is null or length(btrim(note)) between 1 and 2000),
    source        text        not null default 'app' check (source in ('app', 'tool')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint study_assessment_time_has_day check (due_time is null or due_on is not null),
    constraint study_assessment_graded_has_grade check ((status = 'graded') = (grade is not null))
);
comment on table study.study_assessment is 'arga:person';

create index study_assessment_by_due on study.study_assessment (due_on);
create index study_assessment_by_course on study.study_assessment (course_id);

create table study.study_note (
    id            uuid        primary key default gen_random_uuid(),
    course_id     uuid        not null references study.study_course (id) on delete cascade,
    subject_id    uuid        references study.study_subject (id) on delete cascade,
    session_id    uuid        references study.study_session (id) on delete set null,
    title         text        not null default '' check (length(title) <= 200),
    body          text        not null default '' check (length(body) <= 500000),
    search        tsvector    generated always as (
                      setweight(to_tsvector('spanish', title), 'A')
                      || setweight(to_tsvector('spanish', body), 'B')
                  ) stored,
    source        text        not null default 'app' check (source in ('app', 'tool')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table study.study_note is 'arga:person';

create index study_note_search on study.study_note using gin (search);
create index study_note_by_course on study.study_note (course_id, updated_at desc);
create index study_note_by_session on study.study_note (session_id) where session_id is not null;

create table study.study_attachment_link (
    attachment_id uuid        primary key references study.study_attachment (id) on delete cascade,
    note_id       uuid        references study.study_note (id) on delete cascade,
    session_id    uuid        references study.study_session (id) on delete cascade,
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint study_attachment_link_one_owner check ((note_id is null) <> (session_id is null))
);
comment on table study.study_attachment_link is 'arga:person';

create table study.study_material (
    id            uuid        primary key default gen_random_uuid(),
    course_id     uuid        not null references study.study_course (id) on delete cascade,
    subject_id    uuid        references study.study_subject (id) on delete cascade,
    title         text        not null check (length(btrim(title)) between 1 and 200),
    url           text        check (url is null or url ~ '^https?://[^\s]+$'),
    attachment_id uuid        references study.study_attachment (id) on delete cascade,
    created_at    timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint study_material_link_or_file check ((url is null) <> (attachment_id is null))
);
comment on table study.study_material is 'arga:person';

create index study_material_by_course on study.study_material (course_id);

create table study.study_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'study.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table study.study_outbox is 'arga:person';

create index study_outbox_pending on study.study_outbox (id) where published_at is null;

alter table study.study_note add column notebook_id uuid;
create unique index study_note_by_notebook on study.study_note (notebook_id) where notebook_id is not null;

alter table study.study_course
    add column notes_folder text check (notes_folder is null
                                        or (length(btrim(notes_folder)) between 1 and 1000
                                            and notes_folder !~ '(^/|/$|//)'));

alter table study.study_course
    add column tracks text[] not null default '{grades,progress,attendance}'
    check (tracks <@ array['grades', 'progress', 'attendance']::text[]);

create index if not exists study_assessment_subject_id_idx on study.study_assessment (subject_id);
create index if not exists study_assessment_user_id_idx on study.study_assessment (user_id);
create index if not exists study_attachment_user_id_idx on study.study_attachment (user_id);
create index if not exists study_attachment_link_note_id_idx on study.study_attachment_link (note_id);
create index if not exists study_attachment_link_session_id_idx on study.study_attachment_link (session_id);
create index if not exists study_attachment_link_user_id_idx on study.study_attachment_link (user_id);
create index if not exists study_course_certificate_id_idx on study.study_course (certificate_id);
create index if not exists study_course_user_id_idx on study.study_course (user_id);
create index if not exists study_material_attachment_id_idx on study.study_material (attachment_id);
create index if not exists study_material_subject_id_idx on study.study_material (subject_id);
create index if not exists study_material_user_id_idx on study.study_material (user_id);
create index if not exists study_note_subject_id_idx on study.study_note (subject_id);
create index if not exists study_note_user_id_idx on study.study_note (user_id);
create index if not exists study_schedule_subject_id_idx on study.study_schedule (subject_id);
create index if not exists study_schedule_user_id_idx on study.study_schedule (user_id);
create index if not exists study_session_subject_id_idx on study.study_session (subject_id);
create index if not exists study_session_user_id_idx on study.study_session (user_id);
create index if not exists study_subject_user_id_idx on study.study_subject (user_id);

alter table study.study_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists study_outbox_key on study.study_outbox (user_id, type, key, id desc)
    where key is not null;

create function study.study_outbox_notify() returns trigger
language plpgsql as $$
begin
    perform pg_notify('study_outbox', '');
    return null;
end;
$$;

create trigger study_outbox_notify after insert on study.study_outbox
    for each statement execute function study.study_outbox_notify();

drop index if exists study.study_note_search;
alter table study.study_note drop column if exists search;
alter table study.study_note drop column if exists body;
