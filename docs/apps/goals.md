# Goals

Goals, habits and tasks. Tasks are things to do, each in a category, with a due date and time if
needed. Goals are what you set out to achieve: **periodic** (every day or every week, such as
"read 20 minutes, 5 days a week") or **dated** (reach a figure by a date, or a milestone without
one).

Module id `goals`, schema `goals`, role `mod_goals`. Code in [`modules/goals`](../../modules/goals),
manifest in [`manifest.yaml`](../../modules/goals/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/goals/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/goals/` | Tasks: today's ring, the pending tasks by date (overdue, today, tomorrow, next 7 days, later, no date) or by category |
| `/goals/task/<id>` | One task, open in its sheet |
| `/goals/goals` | Goals: how you are doing today, then the active goals by category or by date |
| `/goals/goal/<id>` | One goal: streak, week, consistency or pace and projection, its history and what was logged by hand |
| `/goals/done` | History: closed goals by year, and the tasks done by day |
| `/goals/categories` | Categories: name, colour, order and sharing |
| `/goals/settings` | The app's settings |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Server texts (widgets, panel, the Sunday notice and the default category names) come
from `src/goals/i18n/{en,es}.json`.

## Tasks

- A task always belongs to a category. Each person starts with Work, Home and Personal (and, once
  they open the goals, Health, Money, Learning and Sport), named in their language.
- **Overdue** means its day has passed, or it is today and its time has passed, in the person's
  time zone.
- A **repeating** task has a rule (every Tuesday, every month on the 1st, five times) and its date
  is the first time. Ticking it creates the next one; the done one stays in the history.
- A **shared** category belongs to a space: all its members see and tick its tasks, and each task
  says who ticked it.

## Goals

- A goal tied to a **metric** that another app publishes (steps, weight, net worth, books) is met
  on its own; `list_metrics` lists the ones that have arrived. Without a metric it is logged by
  hand, and a hand-logged day overrides the metric for that day.
- Periodic goals show the streak, the week and the consistency of the last four weeks. Dated goals
  show the current figure, where it should be today, the pace (`ahead`, `on_track`, `behind`) and
  where it lands by the date at this rate.
- A goal is closed as achieved, missed or abandoned, and goes to the History in the year it closed.
  Goals from before using the app can be recorded closed (`record_past_goal`).

## Tools

Read (`goals:read`): `get_categories`, `find_tasks`, `get_goals`, `get_goal`, `list_metrics`.
Write (`goals:write`): `add_task`, `update_task`, `complete_task`, `add_category`, `create_goal`,
`update_goal`, `check_goal`, `close_goal`, `record_past_goal`, `delete_goal`. Their descriptions
are in the [manifest](../../modules/goals/manifest.yaml). `delete_goal` asks for the exact title.

## What it shares with other apps

- **Planner**: every task with a date is an agenda event (`goals.task`), timed when it has a time.
- **Notes**: every goal is a record of kind `Goal` (status, pace, current, target, unit, due,
  closed...), the pending tasks are one record, and each day with tasks done is another.
- **Insights**: the metric `goals.tasks_done`, per day. Goals also **receives** the metrics of the
  other apps, which is how a goal is met on its own.
- **Home**: widgets for today, the next days, the overdue, today's goals, the dated goals and the
  featured goal, and a panel that says what is left for today.
- **Notifications**: on Sunday evening, the weekly goals that will not make it (off by default).

## Demo

[`src/goals/demo.py`](../../modules/goals/src/goals/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): categories in each person's language plus a
shared Household category, eighteen months of tasks done, pending tasks in every state and a
weekly one, a daily reading habit with its checks, a steps goal, a weekly total, a dated savings
goal, a milestone, and two closed goals. It can run any number of times.
