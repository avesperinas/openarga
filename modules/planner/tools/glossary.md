# Planner glossary

- **Layer**: a calendar with its name and tone (Personal, Work, Sport). Every event is in one. A
  hidden layer does not show in the app or the widgets, but its events still exist.
- **Event** or **series**: something with a title, a start and an end. A series is an event with a
  repetition; it is stored once and its occurrences are computed.
- **Occurrence**: each time a series falls on the calendar. It is named by its `original_start`, the
  start its rule gave it even if it was moved later. To touch only one, pass it.
- **Scope** (`scope`): when changing or cancelling something in a series, `this` is only that
  occurrence, `following` that one and the next ones (the series is cut and another starts), `all`
  the whole series.
- **All day**: dates without a time. For the tools, the last day is included ("from the 1st to the
  3rd").
- **Zone**: each event's zone decides daylight saving changes. A series at 10:00 in Madrid stays at
  10:00 after the change. A time without a zone is read in the home zone.
- **Cancel** does not delete: the event stops showing and the row stays.
- **Background**: a layer that shows not as events but as the frame they fall in: working hours, a
  trip. Its items take no time; reads return them apart, in `backgrounds`. Events decide whether
  there is room, and the background says which frame it falls in.
- **Subscribed**: a layer that fills itself from outside (holidays, sport, an `.ics`). It is not
  edited.
