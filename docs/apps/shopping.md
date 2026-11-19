# Shopping

The shopping list that remembers what you buy. One list, by supermarket section, that learns how
often each product is bought and proposes what is due.

Module id `shopping`, schema `shopping`, role `mod_shopping`. Code in
[`modules/shopping`](../../modules/shopping), manifest in
[`manifest.yaml`](../../modules/shopping/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/shopping/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/shopping/` | The list: what is pending by section, what is in the trolley, what is due and the usual products |
| `/shopping/history` | The past trips and what was bought in each |
| `/shopping/settings` | The app's settings, including whose list it is (yours or a space's) |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Section names and server texts come from `src/shopping/i18n/{en,es}.json`. The list
works offline: changes wait in a queue and are sent when the network is back.

## The list

- A **product** is born the first time it is added and is never created twice: names are compared
  ignoring case, accents and extra spaces. It keeps its section and the quantity of the last time.
- **Sections** follow a shop's order: fruit and vegetables, bakery, meat, fish, deli and cheese,
  dairy and eggs, pantry, breakfast and sweets, frozen, drinks, cleaning, personal care and other.
  A new product gets one from a dictionary; changing it is remembered.
- An item is added, put in the trolley, bought or removed. **Finishing a trip** buys what is in
  the trolley; what was not picked up stays for next time.
- **How often** is the median of days between purchases (it needs three), and a product is **due**
  when that long has passed and it is not on the list. Due and usual products are proposals.
- The list can belong to a **space**: everyone in it sees and ticks the same list and trips.

## Tools

Read (`shopping:read`): `get_shopping_list`, `get_purchase_history`.
Write (`shopping:write`): `add_to_list`, `remove_from_list`. Their descriptions are in the
[manifest](../../modules/shopping/manifest.yaml).

## What it shares with other apps

- **`shopping.add`**: another app (Recipes, for a recipe's ingredients) can ask Shopping through
  the kernel to add products to the list.
- **Planner**: each trip is an agenda event (`shopping.trip`).
- **Notes**: each trip is a record.
- **Home**: widgets for the list and for what is due.

## Demo

[`src/shopping/demo.py`](../../modules/shopping/src/shopping/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): one list shared in their space with eighteen months of weekly trips, a long list of products across every aisle, a dozen pending items and three already in the cart.
