# Health (Vitals)

Steps, sleep, heart, weight and lab results. Vitals keeps what you log (weigh-ins, check-ups and
their lab results) and reads what the band and the phone send through the hub (steps, sleep, heart
rate, workouts).

Module id `vitals`, schema `vitals`, role `mod_vitals`. Code in
[`modules/vitals`](../../modules/vitals), manifest in
[`manifest.yaml`](../../modules/vitals/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/vitals/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/vitals/` | Today: steps, sleep, readiness and the day's figures |
| `/vitals/sleep` | Nights, sleep score and patterns |
| `/vitals/training` | Training load and the workouts the band recorded |
| `/vitals/health` | Health: the body figures, heart, weight and labs, each leading to its own screen |
| `/vitals/steps` | Steps by day, week, month and year, against the goal, with the streak |
| `/vitals/weight` | Weigh-ins with the 7-day moving average, the change over 30 and 90 days and the goal band |
| `/vitals/body` | Body composition over time |
| `/vitals/labs` | Check-ups and lab results, each against the reference range of its own report |
| `/vitals/health/heart-day` | The day's heart rate |
| `/vitals/health/rhythm` | Heart rhythm and its alerts |
| `/vitals/health/figure/<key>` | The history of one figure (resting heart rate, HRV, VO₂ max...) |
| `/vitals/settings` | The app's settings: goals, profile and band |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Server texts (widgets, panel, notifications) come from `src/vitals/i18n/{en,es}.json`.

## Key ideas

- The **weight of the day** is the average of that day's weigh-ins; a day without one has none.
  The trend is the 7-day moving average, and the goal is a band with a minimum, a maximum or both.
- **Steps** of a day are the last figure that arrived for it. A day without data is not a day of
  zero steps, and averages only count days with data.
- A **check-up** is a day, a centre and its PDF. Each lab result is compared with the reference
  range printed in its own report.

## Tools

Read (`vitals:read`): `get_kpis`, `get_steps`, `get_weight`, `get_body`, `get_sleep`,
`get_heart_day`, `get_today`, `get_stress`, `get_workouts`, `get_training_load`,
`get_sleep_patterns`, `get_checkup_changes`, `get_heart_rhythm`, `get_band`, `get_lab_results`,
`get_checkups`. Write (`vitals:write`): `log_weight`, `record_checkup`, `add_lab_result`. Their
descriptions are in the [manifest](../../modules/vitals/manifest.yaml).

## What it shares with other apps

- **`weight.log`** and **`workout.heart`**: other apps (Training, Macros) log a weight or ask for a
  workout's heart rate through the kernel.
- **Body weight**: each weigh-in is published as `body_weight` for Training and Macros.
- **Notes**: check-ups and weekly summaries are records.
- **Insights** and **Goals**: steps, weight and other figures as metrics, per day.
- **Home**: widgets for steps, weight, sleep, heart, readiness, training load and the band.
- **Notifications**: band low on battery, band not synced, a new electrocardiogram, irregular
  rhythm alerts.

## Demo

[`src/vitals/demo.py`](../../modules/vitals/src/vitals/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): goals, eighteen months of weigh-ins trending down
(the last ones from today), and four check-ups with seventeen analytes each, Alex's lipids
improving. Steps, daily metrics, sleep, heart rate, band exercises and devices come from
[`demo/health_feed.py`](../../demo/health_feed.py), which `scripts/demo.py` runs after the seeds: it
writes the same events the health provider would send, for eighteen months up to today, with
trends the charts show (resting heart rate falling, HRV rising, more steps). Training sessions and
activities reach Health through the outbox, and the band exercises carry the ids the activities
refer to. It can run any number of times.
