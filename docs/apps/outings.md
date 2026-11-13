# Outings

What is on near you, and what you want to do. Outings keeps two things apart: the **agenda**
(events in your area that someone announced on a page) and your **wishes** (places and plans you
note yourself: somewhere to eat, a plan nearby, a getaway, a trip).

Module id `outings`, schema `outings`, role `mod_outings`. Code in
[`modules/outings`](../../modules/outings), manifest in
[`manifest.yaml`](../../modules/outings/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/outings/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/outings/` | Agenda: a month calendar with what you saved or sent to Planner, today, what is coming and a map of the month |
| `/outings/explore` | The whole agenda: search, when (weekend to a year), where (near or region), what (category), highlights first or by date, what is new and what is for you |
| `/outings/map` | Your wishes and the coming events on the area map, or your wishes on the world map |
| `/outings/wishes` | Wishes in three tabs (outings, restaurants, trips), the archive, and trips being planned in Travel |
| `/outings/events/<id>`, `/outings/wishes/<id>` | One event or one wish |
| `/outings/settings` | Interests (liked and muted words) and plugged agendas |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone.

## The home area

Everything local comes from an **area profile**, a YAML file in
[`modules/outings/areas`](../../modules/outings/areas). Two ship as examples:
[Pamplona](../../modules/outings/areas/pamplona.yaml) and
[Munich](../../modules/outings/areas/munich.yaml). The person's `area` preference picks one,
then `OPENARGA_AREA`, then Pamplona.

| Field | Used for |
|---|---|
| `name`, `country`, `region_code`, `timezone` | Naming the area |
| `language` | The language the AI searches in and writes summaries in |
| `geocoding` | Suffix added when locating a venue (`Hall, Town, <geocoding>`) |
| `stopwords` | Words ignored when two titles are compared to merge duplicates |
| `near.name`, `near.towns`, `near.contains` | The core of the area: an event in one of these towns is `near` |
| `region.name`, `region.towns` | The rest: every other event is `region` |
| `near.box`, `region.box` | The map's two views, `[west, south, east, north]` |
| `map` | Boxes and zoom for the map files, and an optional relief source |
| `focus`, `include`, `skip` | What the brief asks the AI to prioritise, add and leave out |
| `agendas` | Public agenda pages the AI reads first |
| `months`, `searches`, `season`, `traditions` | Web searches, in the area's language, filled with month and year |

To add an area, copy a profile, change the fields, and run the outings tests: every area-sensitive
test runs once per profile. Then build its map:

```bash
node modules/outings/scripts/make-area-map.mjs <area id>
```

It needs Docker (Protomaps and GDAL images) and writes `ui/public/map/<area id>/`: `region.pmtiles`,
`near.pmtiles`, and, when the profile names a relief source, `relief-region.json` and
`relief-near.json`. An area without map files works; the map screen shows the world view only.

## How the agenda fills

- **The AI, every week.** The publisher asks once a week, per person, for an `ai.run` with the
  agenda brief as its task, the week as its key, the `smart` role and web access. The AI reads the
  brief (`get_agenda_brief`), looks at what is there (`find_events`), searches, and adds what it
  finds on a page with `add_events`. Without an AI provider, nothing is added automatically.
- **By hand.** Settings, then Update, copies the same brief to paste into any AI assistant
  connected to OpenArga.
- **Plugged agendas.** Agendas plugged through Connections (`leisure.event`) arrive as events too.

The same event read twice is one, with the links of both. What has passed or is more than a year
away is dropped. Events whose town is in `near.towns` rank higher in "highlights first".

## Tools

Read (`outings:read`): `get_event`, `get_wishes`, `find_place`, `find_events`, `get_agenda_brief`.
Write (`outings:write`): `add_wish`, `update_wish`, `mark_wish_done`, `restore_wish`, `delete_wish`,
`share_wish`, `save_event`, `send_to_calendar`, `add_events`, `hide_events`, `add_interest`,
`remove_interest`. Their descriptions are in the [manifest](../../modules/outings/manifest.yaml).

## What it shares with other apps

- **Planner**: an event sent to Planner is published as `outings.plan` with the agenda contract.
- **Notes**: every wish is a record, and the days you did something are a diary entry.
- **Insights**: the `outings.wishes_done` metric, per day in the person's time zone.
- **Travel**: a trip wish can become a trip idea (`trips.idea`).
- **Notifications**: plans for you, the weekend on Thursday, and something you saved starting
  tomorrow.

## People and spaces

Every row belongs to one person, and Postgres row-level security enforces it. A wish can be shared
with a space: its members see it, edit it and mark it done, but only the person who noted it shares,
unshares or deletes it.

## Demo

[`src/outings/demo.py`](../../modules/outings/src/outings/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): wishes of every kind, some done over eighteen
months, interests, and an agenda in their area's towns relative to today. It can run any number of
times.
