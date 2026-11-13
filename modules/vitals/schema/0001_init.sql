create table vitals.vitals_weight (
    id          uuid         primary key default gen_random_uuid(),
    day         date         not null,
    at          time,
    kg          numeric(5,2) not null check (kg between 20 and 400),
    source      text         not null default 'manual'
                             check (source in ('manual', 'claude', 'history')),
    note        text         check (note is null or length(btrim(note)) between 1 and 200),
    created_at  timestamptz  not null default now(),
    user_id     uuid         not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table vitals.vitals_weight is 'arga:person';

create unique index vitals_weight_once on vitals.vitals_weight (user_id, day, kg);
create index vitals_weight_by_day on vitals.vitals_weight (day desc);

create table vitals.vitals_goal (
    user_id        uuid         primary key
                                default nullif(current_setting('arga.user_id', true), '')::uuid,
    steps_per_day  integer      check (steps_per_day is null or steps_per_day between 100 and 100000),
    weight_min_kg  numeric(5,2) check (weight_min_kg is null or weight_min_kg between 20 and 400),
    weight_max_kg  numeric(5,2) check (weight_max_kg is null or weight_max_kg between 20 and 400),
    updated_at     timestamptz  not null default now(),
    constraint vitals_goal_band_in_order
        check (weight_min_kg is null or weight_max_kg is null or weight_min_kg <= weight_max_kg)
);
comment on table vitals.vitals_goal is 'arga:person';

create table vitals.vitals_outbox (
    id            bigint generated always as identity primary key,
    type          text not null check (type like 'vitals.%'),
    ts            timestamptz not null default now(),
    payload       jsonb not null,
    dedup_hash    text not null,
    published_at  timestamptz,
    attempts      integer not null default 0,
    last_error    text,
    user_id       uuid not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    unique (user_id, dedup_hash)
);
comment on table vitals.vitals_outbox is 'arga:person';

create index vitals_outbox_pending on vitals.vitals_outbox (id) where published_at is null;

create table vitals.vitals_analyte (
    id           text     primary key check (id ~ '^[a-z][a-z0-9_]*$'),
    name         text     not null check (length(btrim(name)) > 0),
    panel        text     not null check (panel in
                          ('blood_count', 'biochemistry', 'lipids', 'urine', 'other')),
    unit         text,
    conversions  jsonb    not null default '{}',
    aliases      text[]   not null default '{}',
    about        text     not null check (length(btrim(about)) > 0),
    position     smallint not null check (position > 0),
    user_id      uuid     default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table vitals.vitals_analyte is 'arga:catalog';

insert into vitals.vitals_analyte (id, name, panel, unit, conversions, aliases, about, position, user_id) values
    ('rbc', 'Red blood cells', 'blood_count', '10^6/µL', '{}', '{red blood cells,rbc,erythrocytes,hematies,eritrocitos,globulos rojos}',
     'Red blood cells per microlitre: the ones that carry oxygen.', 1, null),
    ('hemoglobin', 'Haemoglobin', 'blood_count', 'g/dL', '{"g/L": 0.1}', '{hemoglobin,haemoglobin,hemoglobina,hb}',
     'The protein in red blood cells that carries oxygen.', 2, null),
    ('hematocrit', 'Haematocrit', 'blood_count', '%', '{"L/L": 100}', '{hematocrit,haematocrit,hct,hematocrito,% hematocrito,hto}',
     'The share of the blood taken up by red blood cells.', 3, null),
    ('mcv', 'MCV', 'blood_count', 'fL', '{}', '{mcv,mean corpuscular volume,vcm,volumen corpuscular medio}',
     'The average size of a red blood cell.', 4, null),
    ('mch', 'MCH', 'blood_count', 'pg', '{}', '{mch,mean corpuscular hemoglobin,hcm,hemoglobina corpuscular media}',
     'The average haemoglobin each red blood cell carries.', 5, null),
    ('mchc', 'MCHC', 'blood_count', 'g/dL', '{}', '{mchc,mean corpuscular hemoglobin concentration,chcm,concentracion de hemoglobina corpuscular media}',
     'The average concentration of haemoglobin inside red blood cells.', 6, null),
    ('rdw', 'RDW', 'blood_count', '%', '{}', '{rdw,red cell distribution width,ade,amplitud de distribucion eritrocitaria}',
     'How much the size of red blood cells varies.', 7, null),
    ('wbc', 'White blood cells', 'blood_count', '10^3/µL', '{}', '{white blood cells,wbc,leukocytes,leucocitos,globulos blancos}',
     'White blood cells per microlitre: the defences.', 8, null),
    ('neutrophils', 'Neutrophils', 'blood_count', '10^3/µL', '{}', '{neutrophils,neutrofilos,neutrofilos (v. absoluto)}',
     'Neutrophils per microlitre.', 9, null),
    ('lymphocytes', 'Lymphocytes', 'blood_count', '10^3/µL', '{}', '{lymphocytes,linfocitos,linfocitos (v. absoluto)}',
     'Lymphocytes per microlitre.', 10, null),
    ('monocytes', 'Monocytes', 'blood_count', '10^3/µL', '{}', '{monocytes,monocitos,monocitos (v. absoluto)}',
     'Monocytes per microlitre.', 11, null),
    ('eosinophils', 'Eosinophils', 'blood_count', '10^3/µL', '{}', '{eosinophils,eosinofilos,eosinofilos (v. absoluto)}',
     'Eosinophils per microlitre.', 12, null),
    ('basophils', 'Basophils', 'blood_count', '10^3/µL', '{}', '{basophils,basofilos,basofilos (v. absoluto)}',
     'Basophils per microlitre.', 13, null),
    ('neutrophils_pct', '% neutrophils', 'blood_count', '%', '{}', '{% neutrophils,% neutrofilos,neutrofilos (%)}',
     'The share of white blood cells that are neutrophils.', 14, null),
    ('lymphocytes_pct', '% lymphocytes', 'blood_count', '%', '{}', '{% lymphocytes,% linfocitos,linfocitos (%)}',
     'The share of white blood cells that are lymphocytes.', 15, null),
    ('monocytes_pct', '% monocytes', 'blood_count', '%', '{}', '{% monocytes,% monocitos,monocitos (%)}',
     'The share of white blood cells that are monocytes.', 16, null),
    ('eosinophils_pct', '% eosinophils', 'blood_count', '%', '{}', '{% eosinophils,% eosinofilos,eosinofilos (%)}',
     'The share of white blood cells that are eosinophils.', 17, null),
    ('basophils_pct', '% basophils', 'blood_count', '%', '{}', '{% basophils,% basofilos,basofilos (%)}',
     'The share of white blood cells that are basophils.', 18, null),
    ('platelets', 'Platelets', 'blood_count', '10^3/µL', '{}', '{platelets,plaquetas}',
     'Platelets per microlitre: the ones that clot.', 19, null),
    ('mpv', 'MPV', 'blood_count', 'fL', '{}', '{mpv,mean platelet volume,vpm,vol. plaquetar medio,volumen plaquetar medio}',
     'The average size of a platelet.', 20, null),
    ('esr', 'ESR', 'blood_count', 'mm/h', '{}', '{esr,erythrocyte sedimentation rate,vsg,v.s.g.,velocidad de sedimentacion}',
     'How fast red blood cells settle in one hour.', 21, null),
    ('glucose', 'Glucose', 'biochemistry', 'mg/dL', '{"mmol/L": 18.016}', '{glucose,blood glucose,glucosa,glucosa suero,glucosa en sangre}',
     'Blood sugar, fasting.', 30, null),
    ('urea', 'Urea', 'biochemistry', 'mg/dL', '{"mmol/L": 6.006}', '{urea,serum urea,urea suero}',
     'What is left of proteins, cleared by the kidney.', 31, null),
    ('bun', 'BUN', 'biochemistry', 'mg/dL', '{}', '{bun,blood urea nitrogen,bun suero,nitrogeno ureico}',
     'The nitrogen in urea.', 32, null),
    ('creatinine', 'Creatinine', 'biochemistry', 'mg/dL', '{"µmol/L": 0.011312}', '{creatinine,serum creatinine,creatinina,creatinina suero}',
     'A muscle waste product filtered by the kidney.', 33, null),
    ('egfr', 'Glomerular filtration rate', 'biochemistry', 'mL/min/1.73m²', '{}', '{egfr,glomerular filtration rate,filtrado glomerular,filtrado glomerular estimado,fge,ckd-epi}',
     'How much blood the kidneys filter per minute, estimated.', 34, null),
    ('uric_acid', 'Uric acid', 'biochemistry', 'mg/dL', '{"µmol/L": 0.016811}', '{uric acid,urate,acido urico,acido urico suero,urato}',
     'What is left of the purines in food.', 35, null),
    ('bilirubin', 'Total bilirubin', 'biochemistry', 'mg/dL', '{"µmol/L": 0.058467}', '{total bilirubin,bilirubin,bilirrubina total,bilirrubina total suero}',
     'What is left of old red blood cells, cleared by the liver.', 36, null),
    ('ast', 'AST (GOT)', 'biochemistry', 'U/L', '{}', '{ast,got,ast (got),ast (got) suero,ast [got]}',
     'An enzyme of the liver and the muscle.', 37, null),
    ('alt', 'ALT (GPT)', 'biochemistry', 'U/L', '{}', '{alt,gpt,alt (gpt),alt (gpt) suero,alt [gpt]}',
     'An enzyme mostly of the liver.', 38, null),
    ('ggt', 'Gamma-GT', 'biochemistry', 'U/L', '{}', '{ggt,gamma-gt,gamma-gt suero,gamma gt}',
     'An enzyme of the liver and the bile ducts.', 39, null),
    ('cholesterol', 'Total cholesterol', 'lipids', 'mg/dL', '{"mmol/L": 38.67}', '{cholesterol,total cholesterol,colesterol,colesterol total,colesterol total suero}',
     'All the cholesterol in the blood: the one in LDL, HDL and VLDL.', 50, null),
    ('ldl', 'LDL cholesterol', 'lipids', 'mg/dL', '{"mmol/L": 38.67}', '{ldl,ldl cholesterol,colesterol ldl,ldl colesterol}',
     'The cholesterol carried by LDL, the one that builds up in the arteries.', 51, null),
    ('hdl', 'HDL cholesterol', 'lipids', 'mg/dL', '{"mmol/L": 38.67}', '{hdl,hdl cholesterol,colesterol hdl,hdl colesterol,hdl colesterol suero}',
     'The cholesterol carried by HDL, which takes it away from the tissues.', 52, null),
    ('vldl', 'VLDL cholesterol', 'lipids', 'mg/dL', '{"mmol/L": 38.67}', '{vldl,vldl cholesterol,colesterol vldl,vldl colesterol,vldl colesterol suero}',
     'The cholesterol carried by VLDL, the ones that carry triglycerides.', 53, null),
    ('triglycerides', 'Triglycerides', 'lipids', 'mg/dL', '{"mmol/L": 88.57}', '{triglycerides,trigliceridos,trigliceridos suero}',
     'The fat that circulates in the blood.', 54, null),
    ('non_hdl', 'Non-HDL cholesterol', 'lipids', 'mg/dL', '{"mmol/L": 38.67}', '{non-hdl cholesterol,non hdl,colesterol no hdl,colesterol n-hdl,no hdl}',
     'Total minus HDL: all the cholesterol in the particles that build up.', 55, null),
    ('atherogenic_index', 'Atherogenic index', 'lipids', null, '{}', '{atherogenic index,total cholesterol/hdl,indice aterogenidad,indice aterogenico,colesterol total/hdl}',
     'Total cholesterol divided by HDL.', 56, null),
    ('tg_hdl_ratio', 'TG/HDL ratio', 'lipids', null, '{}', '{tg/hdl ratio,tg/hdl,cociente tg/hdl}',
     'Triglycerides divided by HDL.', 57, null),
    ('fatty_liver_index', 'Fatty liver index', 'other', null, '{}', '{fatty liver index,fli,indice de higado graso}',
     'An estimate of fat in the liver from triglycerides, GGT, weight and waist.', 70, null),
    ('insulin_resistance', 'Insulin resistance', 'other', null, '{}', '{insulin resistance,tyg index,homa,resistencia insulinica,indice tyg}',
     'An estimate of how hard it is for insulin to do its job.', 71, null),
    ('urine_density', 'Specific gravity (urine)', 'urine', null, '{}', '{specific gravity,density,densidad}',
     'How concentrated the urine is.', 80, null),
    ('urine_ph', 'pH (urine)', 'urine', null, '{}', '{ph}',
     'How acidic the urine is.', 81, null),
    ('urine_protein', 'Protein (urine)', 'urine', null, '{}', '{protein,proteinuria,proteinas}',
     'Protein in the urine: expected negative.', 82, null),
    ('urine_glucose', 'Glucose (urine)', 'urine', null, '{}', '{urine glucose,glucosuria,glucosa en orina}',
     'Sugar in the urine: expected negative.', 83, null),
    ('urine_ketones', 'Ketones', 'urine', null, '{}', '{ketones,ketone bodies,cuerpos cetonicos}',
     'What burning fat instead of sugar leaves: expected negative.', 84, null),
    ('urine_bilirubin', 'Bilirubin (urine)', 'urine', null, '{}', '{bilirubinuria,bilirrubinuria,bilirrubina}',
     'Bilirubin in the urine: expected negative.', 85, null),
    ('urine_blood', 'Blood (urine)', 'urine', null, '{}', '{blood,hematuria,sangre}',
     'Blood in the urine: expected negative.', 86, null),
    ('urine_nitrites', 'Nitrites', 'urine', null, '{}', '{nitrites,nitritos}',
     'What some bacteria leave in the urine: expected negative.', 87, null),
    ('urine_urobilinogen', 'Urobilinogen', 'urine', null, '{}', '{urobilinogen,urobilinogeno}',
     'What is left of bilirubin in the urine: expected normal.', 88, null),
    ('urine_leukocytes', 'Leukocytes (urine)', 'urine', null, '{}', '{leukocytes,leukocyturia,leucocituria}',
     'White blood cells in the urine: expected absent.', 89, null);

create table vitals.vitals_checkup (
    id          uuid        primary key default gen_random_uuid(),
    day         date        not null,
    center      text        check (center is null or length(btrim(center)) between 1 and 120),
    notes       text        check (notes is null or length(btrim(notes)) between 1 and 2000),
    created_at  timestamptz not null default now(),
    user_id     uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table vitals.vitals_checkup is 'arga:person';

create unique index vitals_checkup_once
    on vitals.vitals_checkup (user_id, day, (coalesce(center, '')));

create table vitals.vitals_checkup_document (
    checkup_id    uuid        primary key references vitals.vitals_checkup (id),
    filename      text        not null check (length(btrim(filename)) between 1 and 200),
    size          integer     not null check (size between 1 and 20971520),
    content       bytea       not null,
    uploaded_at   timestamptz not null default now(),
    user_id       uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table vitals.vitals_checkup_document is 'arga:person';

create table vitals.vitals_lab_result (
    id           uuid        primary key default gen_random_uuid(),
    checkup_id   uuid        not null references vitals.vitals_checkup (id),
    analyte_id   text        not null references vitals.vitals_analyte (id),
    value        numeric,
    value_text   text        check (value_text is null or length(btrim(value_text)) between 1 and 80),
    unit         text        check (unit is null or length(btrim(unit)) between 1 and 30),
    ref_low      numeric,
    ref_high     numeric,
    created_at   timestamptz not null default now(),
    user_id      uuid        not null default nullif(current_setting('arga.user_id', true), '')::uuid,
    constraint vitals_lab_result_has_value check (value is not null or value_text is not null),
    constraint vitals_lab_result_range_in_order
        check (ref_low is null or ref_high is null or ref_low <= ref_high)
);
comment on table vitals.vitals_lab_result is 'arga:person';

create unique index vitals_lab_result_once on vitals.vitals_lab_result (checkup_id, analyte_id);
create index vitals_lab_result_by_analyte on vitals.vitals_lab_result (analyte_id);

alter table vitals.vitals_goal
    add column weight_direction text check (weight_direction is null or weight_direction in ('up', 'down'));

create index if not exists vitals_analyte_user_id_idx on vitals.vitals_analyte (user_id);
create index if not exists vitals_checkup_document_user_id_idx on vitals.vitals_checkup_document (user_id);
create index if not exists vitals_lab_result_user_id_idx on vitals.vitals_lab_result (user_id);

alter table vitals.vitals_outbox
    add column if not exists key text generated always as (
        case
            when payload ? 'record' then 'record:' || (payload->'record'->>'id')
            when payload ? 'metric' then 'metric:' || (payload->'metric'->>'key') || '@' || (payload->'metric'->>'day')
            when payload ? 'agenda' then 'agenda:' || (payload->'agenda'->>'uid')
        end
    ) stored;

create index if not exists vitals_outbox_key on vitals.vitals_outbox (user_id, type, key, id desc)
    where key is not null;
