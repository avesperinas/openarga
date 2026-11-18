# Training

Strength training, one tap per set, and what the history says. Training follows a **plan** of
days (Push, Pull, Leg...), logs each set as it happens and turns the history into progress per
machine and per muscle.

Module id `training`, schema `training`, role `mod_training`. Code in
[`modules/training`](../../modules/training), manifest in
[`manifest.yaml`](../../modules/training/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/training/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/training/` | Today: the session in progress, or the day the plan has next, and what else was done this week |
| `/training/session/<id>` | One session: its exercises and sets, logged one tap per set |
| `/training/next` | A shortcut that opens the session in progress, or today's screen when there is none |
| `/training/plan` | The plan editor: days, slots, rep ranges and the variants allowed in each slot, in versions |
| `/training/stats` | Progress per variant and per muscle, volume, and the performance index |
| `/training/calendar` | Sessions and other activities by day |
| `/training/settings` | The app's settings: weekly goal, gyms and body weight |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Muscle names and the built-in exercises and variants come from the catalogs:
`exercise.<key>` and `variant.<key>` in `src/training/i18n/{en,es}.json`. An exercise someone
creates keeps the name they wrote.

## Plan, rotation and session

- A **plan** has versions. A published version cannot change; editing writes the next one, valid
  from a date.
- A **rotation** is one full lap of the plan's days, not a week.
- A **session** is a workout: the day, the plan day, the gym, the duration and the sets. Only
  finished sessions are history.

## Load, variants and gyms

An **exercise** is the movement (bench press) and a **variant** is that exercise with an implement
(barbell, Smith machine, machine...). Load is only compared within one variant and at one gym. The
e1RM (Epley) compares sessions with different reps; above ten reps it is marked unreliable, and a
day more than 30 % away from its neighbours does not count. Muscle strength joins each machine's
change into one curve per muscle, and the performance index is their mean, base 100.

## Tools

Read (`training:read`): `find_exercises`, `get_sessions`, `summarise_training`, `get_activities`,
`get_progress`, `get_muscles`. There are no write tools: what is logged in Training is logged while
training. Their descriptions are in the [manifest](../../modules/training/manifest.yaml).

## What it shares with other apps

- **Planner**: sessions and activities are agenda events, and a planned session can be moved from
  the calendar (`agenda.move`).
- **Vitals**: Training asks for the heart rate of a workout (`workout.heart`) and can log a weight
  (`weight.log`); it receives body weight (`body_weight`) for pull-ups and dips, and the band's
  activities.
- **Notes**: sessions are records, and each variant can be linked from a note (`training.variant`).
- **Insights**: training metrics per day, and each workout (`training.workout`).
- **Home**: widgets for the week's training and the next session.

## Demo

[`src/training/demo.py`](../../modules/training/src/training/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): each one's catalogue and gym, a Push Pull Leg plan
published eighteen months ago, and a rotation a week with three sessions whose loads go up every
three weeks. It can run any number of times.
