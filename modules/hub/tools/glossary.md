# Hub glossary

**Connection.** An outside source set up for you: a bank, a calendar, a price source.
You can have several from the same provider, each with its own name.

**Provider.** The source itself (Enable Banking, Bitvavo, Google Health...). Each belongs to a
category, such as Finance, Health, Calendars or Food.

**State of a connection.** It is computed, not stored:

- *up to date*: it worked the last time;
- *expiring*: the permission you gave at the source runs out in less than 14 days;
- *expired*: it ran out, and it has to be authorised again with your biometrics; nobody can do it
  for you;
- *failing*: the last two runs failed for something other than expiry, with the reason the source
  gave;
- *paused*: you stopped it;
- *half done*: you started authorising it and did not come back.

**Set up in its app.** A source that has not moved to Hub yet and is set up in the app that uses
it. It is not missing: it lives somewhere else.

**Four times a day.** The ceiling PSD2 puts on banks without you present. "Up to date" for a bank
means less than six hours old, not this minute.
