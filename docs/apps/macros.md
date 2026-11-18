# Nutrition (Macros)

What you eat and drink, with its macros and micros. Macros logs **entries** (a meal or a drink,
with its time) and works out the day and the week against your target and your references.

Module id `macros`, schema `macros`, role `mod_macros`. Code in
[`modules/macros`](../../modules/macros), manifest in
[`manifest.yaml`](../../modules/macros/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/macros/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/macros/` | Today: the entries, kcal and macros against the target, water and the goals |
| `/macros/day/<date>` | Another day, the same way |
| `/macros/log` | Today with the sheet to log something open |
| `/macros/week` | The week: averages, the trend, what is missing and which foods bring each nutrient |
| `/macros/goals` | The target (kcal, protein, carbs, fat) and the nutrient goals per kind of day |
| `/macros/settings` | The app's settings |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Nutrient names and server texts come from `src/macros/i18n/{en,es}.json`, with one name
in each language for every nutrient of `arga_nutrients`.

## Entries and lines

- An **entry** is a moment when you ate or drank. Its **lines** are of four kinds: a **food** from
  the Recipes pantry (grams, millilitres or units), a **recipe** from Recipes (servings), a
  **quick** estimate (kcal, with the macros if given) and **water**.
- Nutrients are saved when logged and do not change if the food is corrected later; they only move
  if the food is replaced in Recipes, which recalculates what was logged.
- **Coverage** is the share of kcal that brings a nutrient's figure. Below 80 %, the number is not
  reliable, and that is said.
- **Templates** repeat a usual meal in one tap, and a day can be **marked complete**.

## Tools

Read (`macros:read`): `find_food`, `get_day`, `get_week`, `get_suggestions`, `get_usual`,
`get_outdated_recipes`, `get_goals`. Write (`macros:write`): `log_intake`, `mark_day_complete`,
`confirm_intake`, `save_template`, `repeat_intake`, `log_template`, `delete_template`,
`recalculate_recipe_intakes`, `update_intake`, `delete_intake`, `set_target`, `set_goal`,
`set_day_kind`. Their descriptions are in the [manifest](../../modules/macros/manifest.yaml).

## What it shares with other apps

- **Recipes**: foods and recipes come from its pantry (`pantry.*`, `recipes.*`), and Recipes asks
  Macros to recalculate what was logged when a food is replaced (`intake.replace_food`).
- **Vitals**: it receives body weight and workouts, and can log a weight (`weight.log`).
- **Notes**: each day is a record.
- **Insights** and **Goals**: the daily figures (`macros.metric`), per day.
- **Home**: widgets for today, today's macros and goals, what is missing this week, logging and
  compliance.
- **Notifications**: the protein still to go in the evening.

## Demo

[`src/macros/demo.py`](../../modules/macros/src/macros/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): a target, meals logged as quick entries every day
for the last three months and twice a week for the fifteen before, water at lunch, and the past
days marked complete. It can run any number of times.
