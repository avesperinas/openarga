create table vitals.vitals_weight (
    id          uuid         primary key default gen_random_uuid(),
    day         date         not null,
    at          time,
    kg          numeric(5,2) not null check (kg between 20 and 400),
    source      text         not null default 'manual'
                             check (source in ('manual', 'claude', 'historico')),
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
                          ('hemograma', 'bioquimica', 'lipidos', 'orina', 'otros')),
    unit         text,
    conversions  jsonb    not null default '{}',
    aliases      text[]   not null default '{}',
    about        text     not null check (length(btrim(about)) > 0),
    position     smallint not null check (position > 0),
    user_id      uuid     default nullif(current_setting('arga.user_id', true), '')::uuid
);
comment on table vitals.vitals_analyte is 'arga:catalog';

insert into vitals.vitals_analyte (id, name, panel, unit, conversions, aliases, about, position, user_id) values
    ('rbc', 'Hematíes', 'hemograma', '10^6/µL', '{}', '{hematies,eritrocitos,globulos rojos}',
     'Glóbulos rojos por microlitro: los que llevan el oxígeno.', 1, null),
    ('hemoglobin', 'Hemoglobina', 'hemograma', 'g/dL', '{"g/L": 0.1}', '{hemoglobina,hb}',
     'La proteína de los glóbulos rojos que transporta el oxígeno.', 2, null),
    ('hematocrit', 'Hematocrito', 'hemograma', '%', '{"L/L": 100}', '{hematocrito,% hematocrito,hto}',
     'La parte de la sangre que ocupan los glóbulos rojos.', 3, null),
    ('mcv', 'VCM', 'hemograma', 'fL', '{}', '{vcm,volumen corpuscular medio}',
     'El tamaño medio de un glóbulo rojo.', 4, null),
    ('mch', 'HCM', 'hemograma', 'pg', '{}', '{hcm,hemoglobina corpuscular media}',
     'La hemoglobina media que lleva cada glóbulo rojo.', 5, null),
    ('mchc', 'CHCM', 'hemograma', 'g/dL', '{}', '{chcm,concentracion de hemoglobina corpuscular media}',
     'La concentración media de hemoglobina dentro de los glóbulos rojos.', 6, null),
    ('rdw', 'RDW', 'hemograma', '%', '{}', '{rdw,ade,amplitud de distribucion eritrocitaria}',
     'Cuánto varía el tamaño de los glóbulos rojos entre sí.', 7, null),
    ('wbc', 'Leucocitos', 'hemograma', '10^3/µL', '{}', '{leucocitos,globulos blancos}',
     'Glóbulos blancos por microlitro: las defensas.', 8, null),
    ('neutrophils', 'Neutrófilos', 'hemograma', '10^3/µL', '{}',
     '{neutrofilos,neutrofilos (v. absoluto)}', 'Neutrófilos por microlitro.', 9, null),
    ('lymphocytes', 'Linfocitos', 'hemograma', '10^3/µL', '{}',
     '{linfocitos,linfocitos (v. absoluto)}', 'Linfocitos por microlitro.', 10, null),
    ('monocytes', 'Monocitos', 'hemograma', '10^3/µL', '{}', '{monocitos,monocitos (v. absoluto)}',
     'Monocitos por microlitro.', 11, null),
    ('eosinophils', 'Eosinófilos', 'hemograma', '10^3/µL', '{}',
     '{eosinofilos,eosinofilos (v. absoluto)}', 'Eosinófilos por microlitro.', 12, null),
    ('basophils', 'Basófilos', 'hemograma', '10^3/µL', '{}', '{basofilos,basofilos (v. absoluto)}',
     'Basófilos por microlitro.', 13, null),
    ('neutrophils_pct', '% neutrófilos', 'hemograma', '%', '{}', '{% neutrofilos,neutrofilos (%)}',
     'La parte de los leucocitos que son neutrófilos.', 14, null),
    ('lymphocytes_pct', '% linfocitos', 'hemograma', '%', '{}', '{% linfocitos,linfocitos (%)}',
     'La parte de los leucocitos que son linfocitos.', 15, null),
    ('monocytes_pct', '% monocitos', 'hemograma', '%', '{}', '{% monocitos,monocitos (%)}',
     'La parte de los leucocitos que son monocitos.', 16, null),
    ('eosinophils_pct', '% eosinófilos', 'hemograma', '%', '{}', '{% eosinofilos,eosinofilos (%)}',
     'La parte de los leucocitos que son eosinófilos.', 17, null),
    ('basophils_pct', '% basófilos', 'hemograma', '%', '{}', '{% basofilos,basofilos (%)}',
     'La parte de los leucocitos que son basófilos.', 18, null),
    ('platelets', 'Plaquetas', 'hemograma', '10^3/µL', '{}', '{plaquetas}',
     'Plaquetas por microlitro: las que coagulan.', 19, null),
    ('mpv', 'VPM', 'hemograma', 'fL', '{}', '{vpm,vol. plaquetar medio,volumen plaquetar medio}',
     'El tamaño medio de una plaqueta.', 20, null),
    ('esr', 'VSG', 'hemograma', 'mm/h', '{}', '{vsg,v.s.g.,velocidad de sedimentacion}',
     'Lo rápido que se depositan los glóbulos rojos en una hora.', 21, null),
    ('glucose', 'Glucosa', 'bioquimica', 'mg/dL', '{"mmol/L": 18.016}',
     '{glucosa,glucosa suero,glucosa en sangre}', 'El azúcar en sangre, en ayunas.', 30, null),
    ('urea', 'Urea', 'bioquimica', 'mg/dL', '{"mmol/L": 6.006}', '{urea,urea suero}',
     'Lo que queda de las proteínas y elimina el riñón.', 31, null),
    ('bun', 'BUN', 'bioquimica', 'mg/dL', '{}', '{bun,bun suero,nitrogeno ureico}',
     'El nitrógeno de la urea.', 32, null),
    ('creatinine', 'Creatinina', 'bioquimica', 'mg/dL', '{"µmol/L": 0.011312}',
     '{creatinina,creatinina suero}', 'Un desecho del músculo que filtra el riñón.', 33, null),
    ('egfr', 'Filtrado glomerular', 'bioquimica', 'mL/min/1.73m²', '{}',
     '{filtrado glomerular,filtrado glomerular estimado,fge,ckd-epi}',
     'Cuánta sangre filtran los riñones por minuto, estimado.', 34, null),
    ('uric_acid', 'Ácido úrico', 'bioquimica', 'mg/dL', '{"µmol/L": 0.016811}',
     '{acido urico,acido urico suero,urato}', 'Lo que queda de las purinas de la comida.', 35, null),
    ('bilirubin', 'Bilirrubina total', 'bioquimica', 'mg/dL', '{"µmol/L": 0.058467}',
     '{bilirrubina total,bilirrubina total suero}',
     'Lo que queda de los glóbulos rojos viejos, que elimina el hígado.', 36, null),
    ('ast', 'AST (GOT)', 'bioquimica', 'U/L', '{}', '{ast,got,ast (got),ast (got) suero,ast [got]}',
     'Una enzima del hígado y del músculo.', 37, null),
    ('alt', 'ALT (GPT)', 'bioquimica', 'U/L', '{}', '{alt,gpt,alt (gpt),alt (gpt) suero,alt [gpt]}',
     'Una enzima sobre todo del hígado.', 38, null),
    ('ggt', 'Gamma-GT', 'bioquimica', 'U/L', '{}', '{ggt,gamma-gt,gamma-gt suero,gamma gt}',
     'Una enzima del hígado y de las vías biliares.', 39, null),
    ('cholesterol', 'Colesterol total', 'lipidos', 'mg/dL', '{"mmol/L": 38.67}',
     '{colesterol,colesterol total,colesterol total suero}',
     'Todo el colesterol de la sangre: el que va en el LDL, el HDL y el VLDL.', 50, null),
    ('ldl', 'Colesterol LDL', 'lipidos', 'mg/dL', '{"mmol/L": 38.67}',
     '{ldl,colesterol ldl,ldl colesterol}',
     'El colesterol que llevan las LDL, el que se deposita en las arterias.', 51, null),
    ('hdl', 'Colesterol HDL', 'lipidos', 'mg/dL', '{"mmol/L": 38.67}',
     '{hdl,colesterol hdl,hdl colesterol,hdl colesterol suero}',
     'El colesterol que llevan las HDL, que lo retiran de los tejidos.', 52, null),
    ('vldl', 'Colesterol VLDL', 'lipidos', 'mg/dL', '{"mmol/L": 38.67}',
     '{vldl,colesterol vldl,vldl colesterol,vldl colesterol suero}',
     'El colesterol que llevan las VLDL, las que transportan los triglicéridos.', 53, null),
    ('triglycerides', 'Triglicéridos', 'lipidos', 'mg/dL', '{"mmol/L": 88.57}',
     '{trigliceridos,trigliceridos suero}', 'La grasa que circula en la sangre.', 54, null),
    ('non_hdl', 'Colesterol no HDL', 'lipidos', 'mg/dL', '{"mmol/L": 38.67}',
     '{colesterol no hdl,colesterol n-hdl,no hdl}',
     'El total menos el HDL: todo el colesterol de las partículas que se depositan.', 55, null),
    ('atherogenic_index', 'Índice aterogénico', 'lipidos', null, '{}',
     '{indice aterogenidad,indice aterogenico,colesterol total/hdl}',
     'El colesterol total dividido por el HDL.', 56, null),
    ('tg_hdl_ratio', 'Cociente TG/HDL', 'lipidos', null, '{}', '{cociente tg/hdl,tg/hdl}',
     'Los triglicéridos divididos por el HDL.', 57, null),
    ('fatty_liver_index', 'Índice de hígado graso', 'otros', null, '{}',
     '{indice de higado graso,fli,fatty liver index}',
     'Una estimación de grasa en el hígado a partir de triglicéridos, GGT, peso y cintura.', 70, null),
    ('insulin_resistance', 'Resistencia insulínica', 'otros', null, '{}',
     '{resistencia insulinica,indice tyg,homa}',
     'Una estimación de cuánto le cuesta a la insulina hacer su trabajo.', 71, null),
    ('urine_density', 'Densidad (orina)', 'orina', null, '{}', '{densidad}',
     'Lo concentrada que está la orina.', 80, null),
    ('urine_ph', 'pH (orina)', 'orina', null, '{}', '{ph}', 'Lo ácida que es la orina.', 81, null),
    ('urine_protein', 'Proteínas (orina)', 'orina', null, '{}', '{proteinas,proteinuria}',
     'Proteína en la orina: se espera negativa.', 82, null),
    ('urine_glucose', 'Glucosa (orina)', 'orina', null, '{}', '{glucosa en orina,glucosuria}',
     'Azúcar en la orina: se espera negativa.', 83, null),
    ('urine_ketones', 'Cuerpos cetónicos', 'orina', null, '{}', '{cuerpos cetonicos}',
     'Lo que deja quemar grasa en vez de azúcar: se espera negativo.', 84, null),
    ('urine_bilirubin', 'Bilirrubina (orina)', 'orina', null, '{}', '{bilirrubinuria,bilirrubina}',
     'Bilirrubina en la orina: se espera negativa.', 85, null),
    ('urine_blood', 'Sangre (orina)', 'orina', null, '{}', '{sangre,hematuria}',
     'Sangre en la orina: se espera negativa.', 86, null),
    ('urine_nitrites', 'Nitritos', 'orina', null, '{}', '{nitritos}',
     'Lo que dejan algunas bacterias en la orina: se espera negativo.', 87, null),
    ('urine_urobilinogen', 'Urobilinógeno', 'orina', null, '{}', '{urobilinogeno}',
     'Lo que queda de la bilirrubina en la orina: se espera normal.', 88, null),
    ('urine_leukocytes', 'Leucocitos (orina)', 'orina', null, '{}', '{leucocituria}',
     'Glóbulos blancos en la orina: se esperan ausentes.', 89, null);

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
