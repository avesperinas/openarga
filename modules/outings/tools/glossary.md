# Outings glossary

- **Wish**: something the person wants to do and notes down. One of four kinds: **eat** (a place
  to eat or drink), **plan** (something nearby, an afternoon or a day), **getaway** (one or two days
  away, usually within the region) and **trip** (far and longer, which can be just "Japan"). A wish
  keeps a photo, a name, free text and where it is; nothing else: no rating, no company, no budget,
  no itinerary.
- **Done**: marking a wish done takes it off the list and leaves it in the **Archive**, from where it
  can be restored. It goes to no other app: a detailed trip is noted in Travel by hand.
- **Place**: where a wish is, chosen from OpenStreetMap with its name, town, country and
  coordinates. It can be just a name if it could not be located; then it is not on the map.
- **Area**: the person's home area, an area profile (`areas/<id>.yaml`) with its **near** towns (the
  core, such as Pamplona and its comarca) and its **region** (the rest, such as Navarra). Every event
  has a zone, `near` or `region`, from its town.
- **Agenda**: what is on in the area. It comes from the plugged-in agendas and from the AI, which
  reads the brief and adds only what is on a page: every event carries its link.
- **Categories** of an event, a closed list: **eat** (food weeks and days, produce fairs, tastings),
  **stage** (music, theatre, dance, cinema, comedy), **culture** (exhibitions, talks, guided tours,
  books), **festival** (fiestas, traditions, popular fairs, markets) and **outdoors** (sport, nature,
  routes).
- **This weekend** is Friday to Sunday: the coming one from Monday to Thursday, the current one if it
  is already the weekend. A week is seven days from today; a month, thirty; a year, one.
- **Want to go** turns an event into a plan wish with its dates. **To Planner** puts it on the
  calendar. They are different: something can appeal without being decided.
- **Duplicates**: the same event read in two agendas is one, with the links of both.
- **Brief**: the instructions the AI reads before searching (`get_agenda_brief`): which agendas to
  read, what to search for in the area's language, what not to add and how to add it with
  `add_events`.
