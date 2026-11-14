# Calendar (Planner)

Your events, what repeats and what arrives on its own. Planner keeps **layers** (calendars with a
name and a tone) and the **events** in them. A series is stored once with its repetition and its
occurrences are computed; moving or cancelling one occurrence is an override, never a copy.

Module id `planner`, schema `planner`, role `mod_planner`. Code in
[`modules/planner`](../../modules/planner), manifest in
[`manifest.yaml`](../../modules/planner/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/planner/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/planner/day/<date>` | One day, hour by hour |
| `/planner/3days/<date>` | Three days from that one |
| `/planner/week/<date>` | The week of that day, with its ISO week number |
| `/planner/month/<yyyy-mm>` | The month, scrolling by weeks |
| `/planner/agenda/<date>` | A list of the next sixty days |

Without a view, Planner opens the week on a wide screen and three days on a phone. From any view: the
layers (show, hide, rename, recolour, set days off), the subscriptions menu, the event panel and
the app's settings.

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale. The
grid shows instants in the device's zone; everything the server builds (tools, widgets, the home
panel, notices, Notes records) uses the person's time zone. Server texts come from
`src/planner/i18n/{en,es}.json`.

## Layers

- **Own** layers are yours to edit. Each shows either as **events** or as a **background**: the
  frame events fall in (working hours, a trip), which takes no time and is read apart.
- **Subscribed** layers fill themselves from a hub source: holidays, sport, an `.ics` or `webcal://`
  link. They are not edited, but they can be hidden, and a single item can be hidden.
- **App** layers hold what other apps publish to the calendar (a training session, an outing). An
  app may let Planner move its events back; Planner asks it through the kernel (`agenda.move`) and
  shows the app's reason when it refuses.
- A layer that belongs to a space (the demo's Home) is seen by everyone in it. The app does not
  yet offer a way to share one.

## Holidays and days off

The subscriptions menu lists hub's sources (`sources.catalogue`), grouped, with what you already
have. Holidays come from Nager.Date through hub: the national ones of a country and, optionally,
those of one region. The menu proposes the person's country and region from their preferences.
Town holidays are in no public source: put them in a layer of your own, or subscribe to the town's
`.ics` if it publishes one.

Any layer can take its **days off** from other layers: a work background with days off from
Holidays and Local holidays does not show on those days. Only all-day items free a day; what you
put on that day by hand still shows.

## Tools

Read (`planner:read`): `get_calendars`, `get_events`, `get_sources`.
Write (`planner:write`): `create_event`, `update_event`, `cancel_event`, `create_calendar`,
`set_days_off`, `subscribe`, `unsubscribe`. Their descriptions are in the
[manifest](../../modules/planner/manifest.yaml). Repetitions are an object (`freq`, `by_day`,
`until`...), never RRULE text. A time without a zone is read in the person's zone; `scope`
(`this`, `following`, `all`) says how much of a series a change touches.

## What it shares with other apps

- **`agenda`**: Planner receives the events other apps publish and keeps one layer per app.
- **Hub**: subscriptions are hub connections (`sources.plug`, `sources.unplug`), and their runs
  (`hub.run`) say whether a layer is up to date or failing.
- **Notifications**: fifteen minutes before each event of your own visible event layers, and at nine in the
  morning for an all-day one.
- **Notes**: every event is a record (`planner.record`) for its day.
- **Home**: widgets for today, the week, what is up next and this month, and a panel with what is
  left of the day.

## Demo

[`src/planner/demo.py`](../../modules/planner/src/planner/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): a Personal layer with a weekly class, a dentist, a
dinner and a weekend away; a Local holidays layer; a Work background with days off from it; and a
Home layer Alex shares with the space (rent, the weekly shop, a plumber visit). Dates are relative
to today. It can run any number of times.
