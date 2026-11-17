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
