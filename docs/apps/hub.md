# Connections (Hub)

Everything that comes from outside, in one place. Hub keeps the **connections** (a bank, a
calendar subscription, a price source), syncs them on their schedule, and publishes what they bring
as kernel events that the apps consume. Apps never talk to an outside service themselves: they ask
Hub through a capability.

Module id `hub`, schema `hub`, role `mod_hub`. Code in [`modules/hub`](../../modules/hub), manifest
in [`manifest.yaml`](../../modules/hub/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/hub/tools/glossary.md).

## Prices

The `prices` provider values what the person holds, once a day, in euros:

- An instrument is known by its **ISIN** (looked up on onvista and OpenFIGI, which give its funds'
  net asset value or its listing on an exchange) or by its **ticker** as Yahoo Finance writes it
  (`VWCE.DE`, `SPY`). A ticker is the way out for anything the ISIN lookup does not find.
- Instruments are remembered when a portfolio is recorded (the `record_portfolio` tool or a
  statement upload), in the prices connection's `config.instruments`.
- `PRICES_SOURCES` picks the sources, comma separated, from `yahoo` and `onvista` (both by
  default). `PRICES_URL` points Yahoo at another base URL.
- What no source prices is **typed by hand**: the prices connection's screen has a form, and
  `POST /api/hub/prices` takes `{instrument, on, price, name?}` with the price in euros. A typed
  price is one more `finance.price` event, on the same symbol as the remembered line, so Money
  treats it like any other close.
- Cash (`cash`, `liquidez`, `efectivo`) needs no price.

There is no catalogue of funds: anything with an ISIN or a ticker can be priced.

## Institutions

[`catalogs/institutions.toml`](../../modules/hub/src/hub/catalogs/institutions.toml) teaches Hub to
read the movements of a bank: who was paid, the bank's own category, and which movements are
transfers between the person's own accounts. One table per institution, named as the bank
connection names it:

```toml
["Example Bank"]
aliases = ["Example Bank Europe"]                    # other names the bank goes by
internal = "^TRANSFER (TO|FROM) OWN ACCOUNT"         # matches own transfers (case-insensitive)
bank_category = "^CARD PAYMENT AT ([^/]+?) //"       # group 1 is the bank's category
merchant = ["^CARD PAYMENT // (.+)$", "^DIRECT DEBIT (.+)$"]  # first match wins, group 1
```

Every key is optional; an empty table only declares that the institution exists. Patterns are
Python regular expressions run on the movement's description, and `bank_category` and each
`merchant` need one capture group. `tests/test_hub_institutions.py` checks the file. When you add a
bank, add a test with a few real-looking (synthetic) descriptions next to the existing ones.

## Sport calendars

The `football` provider follows any team of the leagues in
[`catalogs/espn.toml`](../../modules/hub/src/hub/catalogs/espn.toml): football (with its domestic
cup and, for European leagues, the UEFA competitions), basketball, American football, baseball and
ice hockey. A football league is stored as its ESPN slug (`esp.1`), any other as `sport/slug`
(`basketball/nba`). To follow a new league, add it to its sport's `leagues` table with its ESPN slug.

Formula 1 (sessions to choose), any iCal address, and public holidays by country and region
(Nager.Date) are the other calendar subscriptions; Planner subscribes to all of them.

## Fake mode

`CONNECTIONS_MODE=fake` sends every outside request of Hub (syncs, capabilities, the worker and
the AI tools) to `hub.fake.transport()` instead of the network. It answers from deterministic
doubles in [`hub/fakes`](../../modules/hub/src/hub/fakes): banks (Enable Banking), Google Health,
holidays, ESPN, Formula 1, any iCal address, prices and exchange rates, weather, books and covers,
food, films, places, nearby, routes, photos, podcasts, agendas, the notes backup on GitHub and web
search. Dates are relative to today, so the data is fresh every day. A request with no double gets
a 503 and is listed in `hub.fake.UNANSWERED`; `tests/test_hub_fake.py` fails if any request leaves
the machine or goes unanswered.

For a fake bank connection use `hub.fakes.bank.APP_ID` and `PEM` as its secrets; for Google Health,
`hub.fakes.google.CLIENT_ID`, `CLIENT_SECRET` and `REFRESH`.
