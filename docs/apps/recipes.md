# Recipes

Your home cookbook, with the nutrition worked out. Recipes keeps the recipes in versions, the
**pantry** of foods with their nutrients per 100 g, and plans the steps of a recipe on a timeline.

Module id `recipes`, schema `recipes`, role `mod_recipes`. Code in
[`modules/recipes`](../../modules/recipes), manifest in
[`manifest.yaml`](../../modules/recipes/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/recipes/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/recipes/` | The recipe book: recipes by category and tag, with time and nutrition |
| `/recipes/recipe/<id>` | One recipe: ingredients for any number of servings, nutrition, and the steps on a timeline |
| `/recipes/recipe/<id>/edit` | The recipe editor |
| `/recipes/new` | A new recipe |
| `/recipes/pantry` | The pantry: foods, their nutrients, portions, aliases and where the figures come from |
| `/recipes/settings` | The app's settings |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Recipe categories and server texts come from `src/recipes/i18n/{en,es}.json`.

## Recipes and versions

- A recipe has servings, ingredients and steps. Editing writes a new **version**; a sealed version
  never changes, so going back is always possible.
- Asking for another number of servings scales the quantities; the saved number does not change.
- Steps have an action, minutes, whether they need attention, where they happen and what they
  depend on, which is what the timeline is drawn from.
- A recipe can be **shared** with a space, and can be archived.

## The pantry

- A **food** has its nutrients per 100 g, imported from USDA or Open Food Facts through the hub, or
  typed by hand with its provenance. A branded food can borrow the micros it lacks from a generic
  one.
- A **portion** is a household measure with its grams (slice, handful, package, serving). An
  **alias** is what you call a food.
- **Replacing** a food swaps it everywhere: recipes get a new version and what was logged in Macros
  is recalculated. The old food is archived, never deleted.

## Tools

Read (`recipes:read`): `find_recipes`, `get_recipe`, `find_foods`, `list_categories`, `list_tags`,
`list_nutrients`. Write (`recipes:write`): `search_food_sources`, `import_food`, `add_manual_food`,
`correct_food`, `set_food_alias`, `replace_food`, `create_recipe`, `update_recipe`,
`delete_recipe`, `archive_recipe`, `unarchive_recipe`, `share_recipe`. Their descriptions are in
the [manifest](../../modules/recipes/manifest.yaml).

## What it shares with other apps

- **Macros**: the pantry and the recipes (`pantry.search`, `pantry.import`, `pantry.nutrients`,
  `recipes.search`, `recipes.nutrients`, `recipes.create`).
- **Shopping**: a recipe's ingredients can go to the list (`shopping.add`).
- **Notes**: every recipe is a record.
- **Home**: widgets for the recipe book and for what can be cooked in half an hour.

## Demo

[`src/recipes/demo.py`](../../modules/recipes/src/recipes/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml) through the module's own `recipes.create`: four
recipes for Alex and three for Sam, with steps, and one shared by each with their space. It can
run any number of times.
