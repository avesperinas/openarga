# Travel

The trips you made, the ones you are planning and the ones you would like to make. Travel keeps
each trip's places, legs, days, bookings, spending, notes, journal and lists, draws everything you
have visited on a map, and turns into a small offline app while you are away.

Module id `travel`, schema `travel`, role `mod_travel`. Code in
[`modules/travel`](../../modules/travel), manifest in
[`manifest.yaml`](../../modules/travel/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/travel/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/travel/` | The map: every country or region you visited, with countries, regions, trips and nights, and filters |
| `/travel/today` | The day of the trip under way: what is next, the day in order, today's journal and spending |
| `/travel/plans` | Ideas without dates and the trips still to come |
| `/travel/trips` | The trips you made by year, other places without a trip, and where you live |
| `/travel/journey` | The trips you made played one after the other on the map |
| `/travel/ideas/<id>` | An idea: its destinations, good months by climate, budget and the trips that came from it |
| `/travel/trips/<id>` | A trip: its summary, figures, map, itinerary, spending, travellers and accounts |
| `/travel/trips/<id>/days`, `/days/<day>` | Day by day, with drag and drop, and one day's route on a street map |
| `/travel/trips/<id>/map` | The whole trip on a street map, day by day, with the saved places |
| `/travel/trips/<id>/bookings` | What is still to book and what is booked, with codes, times and costs |
| `/travel/trips/<id>/money`, `/notes`, `/journal`, `/settings` | The trip's spending, notes, lists and documents, journal, and sharing and offline options |
| `/travel/trips/<id>/edit`, `/travel/new` | The trip editor: details, places, visits, legs and spending |
| `/travel/trip/<id>` | The trip as an app of its own, to add to the home screen |
| `/travel/stats` | Figures: Europe, countries, nights, kilometres, cost per day, by year and month by month |
| `/travel/settings` | The app's settings |

The old Spanish paths (`/travel/viajes/<id>`, `/hoy`, `/planes`, `/estadisticas`...) still open
their screen.

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale.
Server texts that reach the person (widgets, the home panel, records, calendar titles, traveller
names) come from `src/travel/i18n/{en,es}.json`. "Today", trip phases and the calendar follow the
person's time zone; each leg and timed block keeps the zone of its place.

## Trips

- A trip is a plan (dates can still move; it stays in Travel) or confirmed. A confirmed trip is
  upcoming, ongoing or done by its dates, and goes to the calendar.
- **Places**: where you slept (stays, with their nights), what you visited without sleeping there,
  and the legs between them, with their mode and kilometres. Places come from OpenStreetMap
  (`places.search`) and have a kind (restaurant, beach, castle...).
- **Days**: the itinerary per day, with blocks you can order and move, plus the fixed check-ins,
  check-outs and legs. Blocks without a day wait in "No day". Each day has its route
  (`routes.directions`) and what is nearby (`places.nearby`).
- **Bookings**: stays, legs and blocks can carry a booking code, provider, link, times, seat and
  cost; one ticket can cover several legs.
- **Money**: spending is per person in euros, or what was paid in its currency with the rate
  (`fx.rate`), who paid it and how it is split. The accounts show who owes whom and record the
  paybacks.
- **Notes, lists, documents and journal**: notes by category, a packing list and a before-you-go
  list (copyable from another trip), tickets and documents up to 20 MB, and one journal entry per
  day that only its author sees.
- A trip can be shared with a space: the others see it and edit it. Travellers can be tied to the
  space's members.
- **Ideas** are trips without dates: destinations, days, months, budget. Planning one creates a
  trip in plan with its destinations waiting in "No day". Other apps can send ideas
  (`trips.idea`).
- **Offline**: a trip can be prepared for offline use (its days, bookings, documents and map
  tiles). Changes made offline wait and are sent when the network is back.

## Tools

Read (`travel:read`): `get_trips`, `get_trip`, `get_travel`, `find_place`, `find_nearby`,
`get_today`, `get_ideas`, `get_weather`. Write (`travel:write`): `create_trip`, `update_trip`,
`plan_trip`, `confirm_trip`, `unconfirm_trip`, `archive_trip`, `unarchive_trip`, `delete_trip`,
`share_trip`, `add_stay`, `update_stay`, `remove_stay`, `add_visit`, `update_visit`,
`remove_visit`, `add_leg`, `update_leg`, `remove_leg`, `update_place`, `add_block`,
`update_block`, `move_block`, `remove_block`, `update_day`, `record_trip_expense`,
`update_expense`, `remove_expense`, `update_traveller`, `record_settlement`, `remove_settlement`,
`add_trip_note`, `update_trip_note`, `remove_trip_note`, `write_journal`, `add_check_items`,
`check_item`, `remove_check_item`, `copy_checklist`, `add_other_place`, `update_other_place`,
`remove_other_place`, `create_idea`, `update_idea`, `add_idea_place`, `remove_idea_place`,
`plan_idea`, `share_idea`, `archive_idea`, `unarchive_idea`, `delete_idea`. Their descriptions are
in the [manifest](../../modules/travel/manifest.yaml).

## What it shares with other apps

- **Uses**: `places.search`, `places.photo` (covers), `maps.tile`, `routes.directions`,
  `places.nearby`, `weather.forecast`, `weather.climate` and `fx.rate`.
- **Publishes**: `travel.trip`, `travel.leg` and `travel.block` (`agenda`: confirmed trips as
  all-day events, timed legs and blocks); `travel.plan` (`trip`: live trips and plans for the
  other apps); `travel.record` (`record`: a card per trip and per country, a day record while
  travelling and the journal's days); `travel.metric` (`metric`: trips and countries visited).
- **Provides**: `trips.idea`.
- **Home**: widgets for countries, the last trip, the next trip and trips per year, and a panel.

## Demo

[`src/travel/demo.py`](../../modules/travel/src/travel/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): Alex and Sam travel together and apart: trips over eighteen months across Spain, Italy, Germany, Belgium, the Netherlands, Britain, Denmark, France, Morocco and Portugal, the next trip a week away (Copenhagen, with a day-by-day plan, a packing list and things to book), so the week at home in the other apps stays coherent, plans ahead with budgets, ideas for far trips, shared trips with expenses and a settlement between the two of them, and a diary and notes where it fits.
