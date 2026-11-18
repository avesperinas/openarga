alter table training.training_exercise drop constraint if exists training_exercise_key_key;
alter table training.training_variant drop constraint if exists training_variant_key_key;

create unique index if not exists training_exercise_key_per_person
    on training.training_exercise (user_id, key);
create unique index if not exists training_variant_key_per_person
    on training.training_variant (user_id, key);

update training.training_exercise e set key = k.key
from (values
    ('Bench press', 'bench_press'),
    ('Overhead press', 'overhead_press'),
    ('Dips', 'dips'),
    ('Row', 'row'),
    ('Pull-ups', 'pull_ups'),
    ('Biceps curl', 'biceps_curl'),
    ('Squat', 'squat'),
    ('Romanian deadlift', 'romanian_deadlift')
) as k (name, key)
where e.name = k.name and e.key is null
  and not exists (
      select 1 from training.training_exercise o
      where o.key = k.key and o.user_id is not distinct from e.user_id
  );

update training.training_variant v set key = k.key
from (values
    ('Barbell bench press', 'barbell_bench_press'),
    ('Machine chest press', 'machine_chest_press'),
    ('Dumbbell overhead press', 'dumbbell_overhead_press'),
    ('Weighted dips', 'weighted_dips'),
    ('Barbell row', 'barbell_row'),
    ('Weighted pull-ups', 'weighted_pull_ups'),
    ('Cable curl', 'cable_curl'),
    ('Smith machine squat', 'smith_machine_squat'),
    ('Leg press', 'leg_press'),
    ('Barbell Romanian deadlift', 'barbell_romanian_deadlift')
) as k (name, key)
where v.name = k.name and v.key is null
  and not exists (
      select 1 from training.training_variant o
      where o.key = k.key and o.user_id is not distinct from v.user_id
  );
