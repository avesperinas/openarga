# Recipes glossary

The domain terms and how they are worked out. It goes into the agent's context: it is what
separates getting it right from making it up.

**Recipe.** A name, some servings, some ingredients and some steps. What is linked and searched
is the recipe; what is read is its **current version**.

**Version.** A recipe's content at one moment. Once sealed it never changes: editing writes the
next one. That is why `update_recipe` can take the whole recipe without losing anything, and why
you can go back to the previous one (ADR-0042).

**Serving.** How many people the recipe is written for. Asking for another number multiplies the
quantities by `asked / saved`; the saved number does not change.

**Food.** A catalogue entry with its macros **per 100 g**, imported from USDA or Open Food Facts
and cached, or typed by hand when the source does not have it. A recipe ingredient points to a
food; it has no macros of its own.

**Provenance.** Where a typed food's figures come from: "HSN label", "estimated by the model",
"home recipe". It shows on the food's card, because a measured figure and an estimated one are
not worth the same.

**Borrowed micros.** The nutrients a food lacks and takes from another (`micros_from`): the label
macros of a branded product and the micros of the generic USDA entry. Macros are never borrowed,
nor anything the food already has.

**Portion.** A household measure of a food with its edible grams: "slice", "handful". An
ingredient in `unit` with `portion` uses it; without it, `grams_per_unit` counts.

**Replace.** Swapping one food for another everywhere (`replace_food`): the recipes using it get
a new version with the other, what was logged in Macros is recalculated, and the old one is
archived with `replaced_by`. It is not deleted: earlier recipe versions name it.

**Edible share.** What is eaten of what is weighed whole (`edible_fraction`): a 730 g tuna steak
is about 600 g clean, 0.82. It only applies to a quantity marked `as_purchased`.

**Alias.** What you call a food, short and in your language: "chicken breast" for USDA's "Chicken,
broiler or fryers, breast…". It is what the recipe shows and what people type: an ingredient
given by name is looked up first by alias and then by the source's name, which is never touched
because it says where the macros come from. An alias names a single food.

**Unresolved ingredient.** A name someone wrote that is not in the catalogue. It counts as an
ingredient, **adds no macros** and the app asks to resolve it. A similar food is never assigned
to it: that would be lying about the macros.

**Macros.** Kilocalories, protein, fat and carbs. They add up by turning each quantity into
grams: `g` directly, `ml` by density, `tbsp` 15 ml, `tsp` 5 ml, `unit` by the grams of one unit,
`pinch` 0.5 g. `kcal` is not derived from the other three: the source gives it measured.

**Incomplete macros.** Those of a recipe with some ingredient left to convert or resolve. They
come back anyway, with how many are missing out of how many. Half an onion is not 50 g just
because.

**Step.** A verb, a duration in minutes, the appliance it uses and the steps it depends on.

**Attended step.** One that needs you there: chopping, stirring. Two attended steps cannot
overlap, because there is only one person.

**Unattended step.** One that runs by itself: oven, resting, marinating. It frees the cook, and
it is what lets the recipe take less than the sum of its steps.

**Lane.** The appliance a step uses (hob, oven, board…). Two steps in the same lane at once show
in the diagram, which is how you find out they do not fit.

**Total time.** From when you start until you serve, with unattended steps running in parallel.

**Active time.** Of that total, how long you are there. It is the number that decides whether a
recipe fits a Tuesday.
