# Insights

What your data says, every day and every week. Insights reads the figures the other apps publish,
compares each one with your own baseline and only speaks when something passes the bar: a piece of
advice, the Sunday summary, a short reading a day on the topics you like, and things to read, watch
or listen to. Its adviser is called Insights until you give it a name, and you can talk to it.

Module id `insights`, schema `insights`, role `mod_insights`. Code in
[`modules/insights`](../../modules/insights), manifest in
[`manifest.yaml`](../../modules/insights/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/insights/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/insights/` | Today: the pill of the day, the facts of the day, the latest advice and the question of the day |
| `/insights/pill/<id>` | One pill: the reading, "to tell", "to think", the branches to follow, the glossary and the sources |
| `/insights/inbox` | The advice, unread first, with the Sunday summaries |
| `/insights/insight/<id>` | One piece of advice: its figures against their baseline, what it affects, what to do, and a rating |
| `/insights/library` | This week's recommendations as cards, what you saved, and past pills by topic |
| `/insights/you` | What Insights knows of your tastes and where each trait comes from, your topics and sources, and the pill's time, length and language |
| `/insights/chat`, `/insights/chat/<id>`, `/insights/chat/new` | Conversations with the adviser, one per thread, or about one piece of advice |
| `/insights/start` | Getting to know you: a few questions, one at a time |
| `/insights/settings` | The adviser's name and what you tell it about yourself |

The old Spanish paths (`/insights/consejo/<id>`, `/pildora/<id>`, `/biblioteca`...) still open
their screen.

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale.
Server texts that reach the person (widgets, the home panel, notifications, chat problems) come
from `src/insights/i18n/{en,es}.json`, and the briefs ask the model to write in the person's
language. "Today", the schedules and the badge follow the person's time zone.

## Advice and the Sunday summary

- **Signals**: from the `metric` events of the other apps, Insights computes deviations, jumps,
  trends, streaks, stalls, goal paces and crossings, each against the person's own baseline.
- **Morning pass** (between 7:00 and 21:00): if a signal passes the bar, the model writes one piece
  of advice (`alert`) with its figures, what it affects and a concrete action. Most days there is
  none. A topic is not repeated within 30 days unless its figure moves more than 5 %.
- **Weekly pass** (Sunday from 18:00, or Monday until noon): the summary of the week (`weekly`),
  always, with three to seven proposals for next week. Proposals are applied only when the person
  asks an assistant.
- Rating advice (`useful`, `known`, `not_applicable`) raises or lowers the bar on that topic.

## Pills, facts and recommendations

- **Pill**: a few minutes of reading a day on one of the person's topics, written from sources the
  model really read. It is prepared 25 minutes before the chosen time (9:00 by default). Branches
  ask for a follow-up pill; at most three extra pills a day.
- **Facts of the day**: short, true and surprising things from the person's topics, with their
  source.
- **Recommendations** (`picks`): on Friday afternoon or the weekend, books, podcasts, films and more,
  each checked in a catalogue (`books.search`, `podcasts.search`, `films.search`). What is not in
  the catalogue is not published. Saving a book can send it to Library (`books.want`).
- **Tastes**: traits with a stance from −2 to +2. The model proposes them, the person confirms
  them; what the person says is noted as confirmed. The profile pass (Saturday) and the question of
  the day refine them.
- Pills can be listened to: the worker reads them aloud with a local voice when one is installed
  for the pill's language (`INSIGHTS_VOICES_DIR`).

## Chat

Each message to the adviser is a run of the model with arga's read tools; the answer comes back
through the `reply` tool. A thread waits while the run is going on and shows the problem if it
fails. Starting from a piece of advice gives the model that advice and its figures.

## Tools

Read (`insights:read`): `get_profile`, `get_insights`, `get_signals`, `get_series`, `get_runs`,
`get_tastes`, `get_pills`, `get_facts`, `get_library`. Write (`insights:write`):
`publish_insight`, `reply`, `publish_pill`, `publish_facts`, `publish_picks`, `ask_question`,
`propose_trait`, `note_taste`, `rate_insight`. Their descriptions are in the
[manifest](../../modules/insights/manifest.yaml).

## What it shares with other apps

- **Uses**: `claude.run` (the passes, pills and chat), `notify.sync`, and the catalogues
  `books.search`, `books.cover`, `books.want`, `podcasts.search` and `films.search`.
- **Receives**: `metric` (the signals) and `record`.
- **Publishes**: `insights.record` (`record` contract): a card per Sunday summary (`Week summary`
  in `Weeks`, with a `week` property) and per pill (`Pill` in `Pills`), which Notebook keeps as
  notes.
- **Notifications**: new advice, the pill of the day, the question of the day and this week's
  recommendations.
- **Home**: widgets for the latest advice and today's pill, a panel and a badge.

## Demo

[`src/insights/demo.py`](../../modules/insights/src/insights/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): what they tell about themselves, a few tastes,
last Sunday's summary, one piece of advice from today, yesterday's pill (read) and today's
(unread). Dates are relative to today. It can run any number of times.
