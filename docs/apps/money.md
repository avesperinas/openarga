# Finance

Your accounts, your investments, the expenses you share and what everything is worth. It reads
movements from your banks, or from the files you import, and turns them into net worth, cash, an
emergency fund, spending and a monthly balance with whoever you share a home with.

Module id `money`, schema `money`, role `mod_money`. Code in
[`modules/money`](../../modules/money), manifest in
[`manifest.yaml`](../../modules/money/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/money/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/money/` | Summary: net worth, liquid, cash, emergency fund and monthly spending, each against a year ago |
| `/money/movements` | The movements of your accounts, what each one is for, and what waits for you to label it |
| `/money/shared` | Shared expenses by year, who paid what and who owes whom |
| `/money/analysis` | Worth, investments, composition, spending by category, income against spending, and the monthly circuit |
| `/money/settings` | Accounts and products, categories, rules, incomes and the space you share with |

Two things are done from a product's sheet in Settings. On a current or savings account, **Import a
file** takes a CSV or OFX, shows its first rows, says how many lines it has and imports it; if a CSV's
columns are not recognised it asks which hold the date, the description and the amount. On an
investment product, **Edit positions** lists what was bought with its value and gain, and adds, edits
or removes a position (ISIN or ticker, units, total cost, and optionally a price and its day).

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Server texts come from `src/money/i18n/{en,es}.json`. Amounts are shown in the
**base currency**, which comes from the person's preferences (`arga_module.preferences.current()`);
nothing is hard-coded to the euro.

## Where the data comes from

- **Bank by API.** The accounts of a connection made in Hub arrive as the `finance.account`,
  `finance.movement`, `finance.movement_detail`, `finance.balance`, `finance.holding` and
  `finance.price` events. Money matches each source account to one of yours by bank and IBAN tail
  or name.
- **CSV and OFX files.** `POST /api/money/accounts/{key}/statement` takes the text of a CSV or an
  OFX file (SGML or XML, read by hand) and adds its lines and closing balance to the account.
  CSV delimiters, `1.234,56` and `1,234.56`, a single amount column or debit and credit columns
  are all understood; `columns` names the ones that are unusual. Importing a file twice adds
  nothing. Imported lines are `statement` movements and are only yours.
- **By hand.** A product without a source is valued by what you write down: a property, a deposit.

## Products and investments

- A **product** is an account of yours: current, savings, fund, ETF or shares, pension plan,
  property or deposit. Each counts by your share, and the shared one counts half.
- **Investments are a snapshot of what was bought.** A position is an ISIN or a ticker, the units
  and what they cost in total. Its price is the latest one Hub publishes for that ISIN or ticker;
  without one, the price you wrote with its date; without either, what was paid. The card says
  which, and shows value and gain. A product with positions is valued by them
  (`GET/PUT /accounts/{key}/positions`, `DELETE /accounts/{key}/positions/{symbol}`).
- **There is no catalogue of funds.** You say what a fund is, its asset class and its split by
  region, and the composition uses it. What you did not classify shows as "no breakdown".
- There are no taxes, no fund certificates, no crypto and no entries by mail.

## Spending and sharing

- Every movement is **an expense, an income, a transfer between your accounts or a return**. Rules
  (by text, merchant, amount, account or the bank's own category) decide it; what no rule decides
  waits for a label, and a label can become a rule.
- **Shared expenses** are entered by whoever paid and split fifty-fifty or by income. Each year
  shows who owes whom, and can be settled.
- **Emergency fund**: one account takes that role and is measured against months of basic spending.

## Tools

Read (`money:read`): `get_summary`, `get_movements`, `get_shared_balance`, `get_products`,
`get_composition`, `get_positions`, `get_rules`.
Write (`money:write`): `categorise_movement`, `mark_transfer`, `record_shared_expense`,
`create_product`, `update_product`, `record_composition`, `record_value`, `record_position`,
`classify_fund`, `delete_rule`. Their descriptions are in the
[manifest](../../modules/money/manifest.yaml).

## What it shares with other apps

- **Hub**: banks, balances, holdings and prices arrive through its connections.
- **Home**: widgets for net worth, liquid, cash, the emergency fund and monthly spending.
- **Metrics**: monthly figures are published as `money.metric`, which other apps can read.

## Demo

[`src/money/demo.py`](../../modules/money/src/money/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): eighteen months of an everyday account and a savings account with movements across food, restaurants, health, shopping, sport, phone, travel and subscriptions (flights and hotels match the trips in Travel), a few movements left to label, month-end balances so the net worth curve is smooth, a brokerage account with positions, and shared expenses between Alex and Sam (rent, utilities, groceries, dinners out, home) written from both points of view so the balance shows on both sides.
