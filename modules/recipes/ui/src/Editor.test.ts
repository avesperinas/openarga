import { canSave, draftOf, toRequest, withoutIngredient, withoutStep } from "./Editor";
import type { Recipe } from "./api";

const RECIPE: Recipe = {
  id: "r1",
  name: "Porrusalda",
  servings: 4,
  requested_servings: 6,
  space_id: null,
  mine: true,
  version: 2,
  versions: 2,
  source: "app",
  note: null,
  tags: [
    { id: "t1", name: "invierno", emoji: null },
    { id: "t2", name: "olla", emoji: null },
  ],
  groups: [
    {
      category_id: "vegetable",
      name: "Verdura",
      emoji: "🥬",
      ingredients: [
        {
          position: 1,
          name: "Puerro",
          food_id: "f1",
          category_id: "vegetable",
          quantity: 600,
          unit: "g",
          note: "en rodajas",
          optional: false,
          grams: 600,
        },
      ],
    },
    {
      category_id: "other",
      name: "Otros",
      emoji: "🧂",
      ingredients: [
        {
          position: 2,
          name: "Sofrito de la abuela",
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
    uncertainty: "falta 1 de 2 ingredientes (Sofrito de la abuela)",
  },
};

test("se edita lo guardado, no lo que se está mirando escalado", () => {
  const draft = draftOf(RECIPE);

  expect(draft.servings).toBe(4);
  expect(draft.ingredients[0]?.quantity).toBe(400);
  expect(draft.ingredients[1]?.quantity).toBe(1);
});

test("los ingredientes vuelven en el orden en que se escribieron, no por categoría", () => {
  const draft = draftOf(RECIPE);

  expect(draft.ingredients.map((one) => one.label)).toEqual(["Puerro", "Sofrito de la abuela"]);
});

test("un ingrediente sin resolver se sigue guardando por su nombre", () => {
  const body = toRequest(draftOf(RECIPE));

  expect(body.ingredients[1]).toMatchObject({ food_id: null, name: "Sofrito de la abuela" });
  expect(body.ingredients[0]).toMatchObject({ food_id: "f1", name: null });
});

test("las etiquetas se escriben separadas por comas y se limpian", () => {
  const draft = { ...draftOf(RECIPE), tags: " invierno ,, olla , " };

  expect(toRequest(draft).tags).toEqual(["invierno", "olla"]);
});

test("sin nombre o sin ingredientes no se puede guardar", () => {
  const draft = draftOf(RECIPE);

  expect(canSave(draft)).toBe(true);
  expect(canSave({ ...draft, name: "  " })).toBe(false);
  expect(canSave({ ...draft, ingredients: [] })).toBe(false);
});

test("quitar un paso renumera lo que iba detrás", () => {
  const steps = [
    { action: "chop", text: "Picar", minutes: 5, attended: true, equipment: "board", after: [], ingredients: [] },
    { action: "saute", text: "Pochar", minutes: 10, attended: true, equipment: "hob", after: [1], ingredients: [] },
    { action: "simmer", text: "Cocer", minutes: 30, attended: false, equipment: "hob", after: [2], ingredients: [] },
  ];

  const left = withoutStep(steps, 0);

  expect(left.map((one) => one.text)).toEqual(["Pochar", "Cocer"]);
  expect(left.map((one) => one.after)).toEqual([[], [1]]);
});

test("un paso que empezaba a la vez que el anterior lo sigue haciendo al renumerar", () => {
  const steps = [
    { action: "bake", text: "Hornear", minutes: 40, attended: false, equipment: "oven", after: [], ingredients: [] },
    { action: "chop", text: "Picar", minutes: 10, attended: true, equipment: "board", after: [], ingredients: [] },
    { action: "serve", text: "Servir", minutes: 5, attended: true, equipment: "none", after: [2], ingredients: [] },
  ];

  const left = withoutStep(steps, 2);

  expect(left.map((one) => one.after)).toEqual([[], []]);
});

test("los pasos guardados vuelven al editor enteros, con lo que entra en cada uno", () => {
  const withSteps = {
    ...RECIPE,
    kitchen: {
      ...RECIPE.kitchen,
      steps: [
        { position: 1, action: "chop", text: "Picar", minutes: 5, attended: true, equipment: "board", ingredients: ["Puerro"], uses: [1], after: [], start: 0, end: 5 },
        { position: 2, action: "simmer", text: "Cocer", minutes: 30, attended: false, equipment: "hob", ingredients: [], uses: [], after: [1], start: 5, end: 35 },
        { position: 3, action: "serve", text: "Servir", minutes: 2, attended: true, equipment: "none", ingredients: ["Sofrito de la abuela"], uses: [2], after: [1, 2], start: 35, end: 37 },
      ],
      total_minutes: 37,
      active_minutes: 7,
      lanes: ["hob", "board"],
      overlaps: [],
    },
  };

  const draft = draftOf(withSteps);

  expect(draft.steps.map((one) => one.text)).toEqual(["Picar", "Cocer", "Servir"]);
  expect(draft.steps[1]?.attended).toBe(false);
  expect(draft.steps[2]?.after).toEqual([1, 2]);
  expect(draft.steps[0]?.ingredients).toEqual([1]);
  expect(draft.steps[2]?.ingredients).toEqual([2]);
});

test("quitar un paso se lleva las dependencias que apuntaban a él", () => {
  const steps = [
    { action: "chop", text: "Picar", minutes: 5, attended: true, equipment: "board", after: [], ingredients: [1] },
    { action: "saute", text: "Pochar", minutes: 10, attended: true, equipment: "hob", after: [], ingredients: [2] },
    { action: "simmer", text: "Cocer", minutes: 30, attended: false, equipment: "hob", after: [1, 2], ingredients: [] },
  ];

  const left = withoutStep(steps, 1);

  expect(left.map((one) => one.text)).toEqual(["Picar", "Cocer"]);
  expect(left[1]?.after).toEqual([1]);
});

test("quitar un ingrediente lo quita también de los pasos que lo usaban", () => {
  const draft = {
    name: "Porrusalda",
    servings: 4,
    tags: "",
    ingredients: [
      { food_id: "f1", quantity: 400, unit: "g" as const, label: "Puerro" },
      { food_id: "f2", quantity: 30, unit: "ml" as const, label: "Aceite" },
      { food_id: "f3", quantity: 600, unit: "g" as const, label: "Patata" },
    ],
    steps: [
      { action: "chop", text: "Picar", minutes: 5, attended: true, equipment: "board", after: [], ingredients: [1, 2] },
      { action: "simmer", text: "Cocer", minutes: 30, attended: false, equipment: "hob", after: [1], ingredients: [3] },
    ],
  };

  const left = withoutIngredient(draft, 0);

  expect(left.ingredients.map((one) => one.label)).toEqual(["Aceite", "Patata"]);
  expect(left.steps[0]?.ingredients).toEqual([1]);
  expect(left.steps[1]?.ingredients).toEqual([2]);
});
