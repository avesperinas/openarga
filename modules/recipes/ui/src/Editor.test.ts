import { canSave, draftOf, toRequest, withoutIngredient, withoutStep } from "./Editor";
import type { Recipe } from "./api";

const RECIPE: Recipe = {
  id: "r1",
  name: "Leek soup",
  servings: 4,
  requested_servings: 6,
  space_id: null,
  mine: true,
  version: 2,
  versions: 2,
  source: "app",
  note: null,
  tags: [
    { id: "t1", name: "winter", emoji: null },
    { id: "t2", name: "pot", emoji: null },
  ],
  groups: [
    {
      category_id: "vegetable",
      name: "Vegetables",
      emoji: "🥬",
      ingredients: [
        {
          position: 1,
          name: "Leek",
          food_id: "f1",
          category_id: "vegetable",
          quantity: 600,
          unit: "g",
          note: "sliced",
          optional: false,
          grams: 600,
        },
      ],
    },
    {
      category_id: "other",
      name: "Other",
      emoji: "🧂",
      ingredients: [
        {
          position: 2,
          name: "Grandma's sofrito",
          food_id: null,
          category_id: "other",
          quantity: 1.5,
          unit: "unit",
          note: null,
          optional: false,
          grams: null,
        },
      ],
    },
  ],
  kitchen: { steps: [], grid: { rows: [], cells: [], bands: [], columns: 0, notes: [] }, total_minutes: 0, active_minutes: 0, lanes: [], overlaps: [] },
  nutrition: {
    total: { kcal: 0, protein: 0, fat: 0, carbs: 0, fiber: null, salt: null },
    per_serving: { kcal: 0, protein: 0, fat: 0, carbs: 0, fiber: null, salt: null },
    counted: 1,
    ingredients: 2,
    uncertainty: "1 of 2 ingredients missing (Grandma's sofrito)",
  },
};

test("what is saved is edited, not the scaled view", () => {
  const draft = draftOf(RECIPE);

  expect(draft.servings).toBe(4);
  expect(draft.ingredients[0]?.quantity).toBe(400);
  expect(draft.ingredients[1]?.quantity).toBe(1);
});

test("ingredients come back in the order they were written, not by category", () => {
  const draft = draftOf(RECIPE);

  expect(draft.ingredients.map((one) => one.label)).toEqual(["Leek", "Grandma's sofrito"]);
});

test("an unresolved ingredient is still saved by its name", () => {
  const body = toRequest(draftOf(RECIPE));

  expect(body.ingredients[1]).toMatchObject({ food_id: null, name: "Grandma's sofrito" });
  expect(body.ingredients[0]).toMatchObject({ food_id: "f1", name: null });
});

test("tags are written separated by commas and cleaned", () => {
  const draft = { ...draftOf(RECIPE), tags: " winter ,, pot , " };

  expect(toRequest(draft).tags).toEqual(["winter", "pot"]);
});

test("without a name or ingredients it cannot be saved", () => {
  const draft = draftOf(RECIPE);

  expect(canSave(draft)).toBe(true);
  expect(canSave({ ...draft, name: "  " })).toBe(false);
  expect(canSave({ ...draft, ingredients: [] })).toBe(false);
});

test("removing a step renumbers what came after", () => {
  const steps = [
    { action: "chop", text: "Chop", minutes: 5, attended: true, equipment: "board", after: [], ingredients: [] },
    { action: "saute", text: "Soften", minutes: 10, attended: true, equipment: "hob", after: [1], ingredients: [] },
    { action: "simmer", text: "Simmer", minutes: 30, attended: false, equipment: "hob", after: [2], ingredients: [] },
  ];

  const left = withoutStep(steps, 0);

  expect(left.map((one) => one.text)).toEqual(["Soften", "Simmer"]);
  expect(left.map((one) => one.after)).toEqual([[], [1]]);
});

test("a step that started with the previous one still does after renumbering", () => {
  const steps = [
    { action: "bake", text: "Bake", minutes: 40, attended: false, equipment: "oven", after: [], ingredients: [] },
    { action: "chop", text: "Chop", minutes: 10, attended: true, equipment: "board", after: [], ingredients: [] },
    { action: "serve", text: "Serve", minutes: 5, attended: true, equipment: "none", after: [2], ingredients: [] },
  ];

  const left = withoutStep(steps, 2);

  expect(left.map((one) => one.after)).toEqual([[], []]);
});

test("saved steps come back to the editor whole, with what goes into each", () => {
  const withSteps = {
    ...RECIPE,
    kitchen: {
      ...RECIPE.kitchen,
      steps: [
        { position: 1, action: "chop", text: "Chop", minutes: 5, attended: true, equipment: "board", ingredients: ["Leek"], uses: [1], after: [], start: 0, end: 5 },
        { position: 2, action: "simmer", text: "Simmer", minutes: 30, attended: false, equipment: "hob", ingredients: [], uses: [], after: [1], start: 5, end: 35 },
        { position: 3, action: "serve", text: "Serve", minutes: 2, attended: true, equipment: "none", ingredients: ["Grandma's sofrito"], uses: [2], after: [1, 2], start: 35, end: 37 },
      ],
      total_minutes: 37,
      active_minutes: 7,
      lanes: ["hob", "board"],
      overlaps: [],
    },
  };

  const draft = draftOf(withSteps);

  expect(draft.steps.map((one) => one.text)).toEqual(["Chop", "Simmer", "Serve"]);
  expect(draft.steps[1]?.attended).toBe(false);
  expect(draft.steps[2]?.after).toEqual([1, 2]);
  expect(draft.steps[0]?.ingredients).toEqual([1]);
  expect(draft.steps[2]?.ingredients).toEqual([2]);
});

test("removing a step takes the dependencies pointing to it", () => {
  const steps = [
    { action: "chop", text: "Chop", minutes: 5, attended: true, equipment: "board", after: [], ingredients: [1] },
    { action: "saute", text: "Soften", minutes: 10, attended: true, equipment: "hob", after: [], ingredients: [2] },
    { action: "simmer", text: "Simmer", minutes: 30, attended: false, equipment: "hob", after: [1, 2], ingredients: [] },
  ];

  const left = withoutStep(steps, 1);

  expect(left.map((one) => one.text)).toEqual(["Chop", "Simmer"]);
  expect(left[1]?.after).toEqual([1]);
});

test("removing an ingredient also removes it from the steps that used it", () => {
  const draft = {
    name: "Leek soup",
    servings: 4,
    tags: "",
    ingredients: [
      { food_id: "f1", quantity: 400, unit: "g" as const, label: "Leek" },
      { food_id: "f2", quantity: 30, unit: "ml" as const, label: "Oil" },
      { food_id: "f3", quantity: 600, unit: "g" as const, label: "Potato" },
    ],
    steps: [
      { action: "chop", text: "Chop", minutes: 5, attended: true, equipment: "board", after: [], ingredients: [1, 2] },
      { action: "simmer", text: "Simmer", minutes: 30, attended: false, equipment: "hob", after: [1], ingredients: [3] },
    ],
  };

  const left = withoutIngredient(draft, 0);

  expect(left.ingredients.map((one) => one.label)).toEqual(["Oil", "Potato"]);
  expect(left.steps[0]?.ingredients).toEqual([1]);
  expect(left.steps[1]?.ingredients).toEqual([2]);
});
