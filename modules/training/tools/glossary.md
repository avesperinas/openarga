# Training glossary

What you need to know to answer about training without making anything up. It goes with the tools,
all of them read-only: what is logged in Training is logged while training.

- `find_exercises`: the index. Turns a name into the variant the person trains with.
- `get_sessions`: finished workouts, with a date range. Returns **the range total** besides the
  ones that fit in `limit`: if `returned` is lower than `total`, the list is cut and you have to
  ask for a smaller range or a higher limit, never assume that is all.
- `summarise_training`: counts workouts, hours and volume by year, month, week, day kind or gym.
  **It is the one that answers "how many workouts did I do in 2025"**: no need to read session by
  session, and it has no row cap.
- `get_progress`: the load of one variant over time, split by gym, with the best day of the
  period and the days that do not count, each with its reason.
- `get_muscles`: the strength of each muscle group in a range, its sets per week and what worked
  it. **It is the one that answers "how is my chest doing?"** or "which muscle is lagging?".
- `get_activities`: what is not strength: climbing, padel, whatever was logged.

## Variant, gym, and why load is only compared within one machine

An **exercise** is the movement: bench press, squat, pull-up. A **variant** is that exercise with
a specific implement (barbell, dumbbell, Smith machine, machine, cable, bodyweight).

The hard rule of the domain: **load is only compared within one variant and at a single gym**.
140 kg on the Smith machine and 80 kg on the leg press are neither added nor compared, because
they do not measure the same thing; and the same lat pulldown at two gyms neither, because they
are two different cables. If the machine changed at a gym, `get_progress` marks that day with
`machine_changed`, and what came before is not compared with what came after. That is why
`get_progress` asks for a variant and not a name, and why `find_exercises` exists: to turn "how is
my bench press doing?" into the variant that person really trains with. If several fit, ask which
one before comparing; do not pick one.

## Days that do not count

A day whose e1RM is more than 30 % away from the surrounding sessions on the same machine does not
count for strength: it is almost always a mistyped entry (140 where 104 was meant, the pair of
dumbbells where one was meant). `get_progress` returns it with `counts: false` and the reason in
`why_not`. It is neither deleted nor corrected from here: mention it as doubtful or do not mention
it, and never use it as a record.

## Set, reps and load

A **set** is a run of reps with one load. It may carry:

- `weight`: external load, in kilograms.
- `added_load`: load added on top of bodyweight. In pull-ups, `4 × 20 kg` is four reps with twenty
  kilograms hanging, not with twenty kilograms in total.
- A **not completed** set is one logged without reps. It does not count, and it is not filled in
  by guessing.

An **effective set** is one that counts for a muscle group: each set counts in full for the
primary muscle of its exercise and for no other. The lat pulldown is lats; that the biceps work
does not turn it into a biceps set.

## Session and rotation

A **session** is a workout: the day, the plan day that was due (Push, Pull, Leg...), its duration
and its sets. An **unfinished** session is in progress and is not history: it does not appear in
`get_sessions` and does not enter any comparison.

A **rotation** is one full lap of the plan. It is not a week: if the plan has three days and the
person trains four times a week, rotations and weeks do not match. "Day 2 of 3" is the position in
the current rotation.

## e1RM, and when not to trust it

The **e1RM** is the estimated one-rep max, computed from a normal set with the Epley formula:
`load × (1 + reps / 30)`. It allows comparing sessions where the reps were not the same.

It is an estimate, and above **ten reps it stops being reliable**: with many reps endurance rules,
not maximal strength. `get_progress` says so on every data point with `e1rm_reliable`, and a point
marked as unreliable is mentioned as such or not mentioned. Sets of more than fifteen reps and sets
of zero (a failure) do not count for strength.

## Muscle strength and performance index

The strength of a muscle comes from comparing each machine with itself: how much each one goes up
or down against its previous sessions, joined into one curve per muscle. Changing gym, machine or
exercise does not move it; neither do the first three weeks of a new exercise, because at the start
you get stronger by learning, not by gaining strength. `get_muscles` gives it as % change in the
range.

The **performance index** is the mean of the muscles with data, base 100, every muscle with the
same weight. In pull-ups and dips the load is bodyweight plus the added load: without a bodyweight
in Settings, those exercises do not count for strength (`bodyweight_kg` is `null`).

## Counting, and not mistaking cut for complete

For how many, how much or when, `summarise_training`. To see the workouts, `get_sessions` with its
range. Every answer that comes from a list carries `total` and `returned`: if they differ, what you
see is a part, and stating a number from there is making it up.

## What cannot be answered

- **Nothing about another person.** Everyone sees their own, and the database guarantees it.
- **Nothing that is not logged.** If a variant has no sets, the answer is that there is no data,
  not an average of others.
- **No medical or rehabilitation advice.** Pain is not training data.
