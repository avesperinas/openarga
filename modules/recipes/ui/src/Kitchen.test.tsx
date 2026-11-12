import { renderToString } from "react-dom/server";

import { KitchenPlan, KitchenTimes } from "./Kitchen";
import type { Ingredient, Kitchen } from "./api";

const INGREDIENTS: Ingredient[] = [
  { position: 1, name: "Puerro", food_id: "f1", category_id: "vegetable", quantity: 400, unit: "g", note: null, optional: false, grams: 400 },
  { position: 2, name: "Patata", food_id: "f2", category_id: "vegetable", quantity: 600, unit: "g", note: null, optional: false, grams: 600 },
];

const KITCHEN: Kitchen = {
  steps: [
    { position: 1, action: "chop", text: "Picar el puerro", minutes: 5, attended: true, equipment: "board", ingredients: ["Puerro"], uses: [1], after: [], start: 0, end: 5 },
    { position: 2, action: "simmer", text: "Cocer a fuego lento", minutes: 30, attended: false, equipment: "hob", ingredients: ["Patata"], uses: [2], after: [1], start: 5, end: 35 },
  ],
  grid: {
    rows: [
      { position: 1, name: "Puerro", orphan: false },
      { position: 2, name: "Patata", orphan: false },
    ],
    cells: [
      { position: 1, action: "chop", text: "Picar el puerro", minutes: 5, attended: true, equipment: "board", column: 1, row: 1, span: 1 },
      { position: 2, action: "simmer", text: "Cocer a fuego lento", minutes: 30, attended: false, equipment: "hob", column: 2, row: 1, span: 2 },
    ],
    bands: [],
    columns: 2,
    notes: [],
  },
  total_minutes: 35,
  active_minutes: 5,
  lanes: ["hob", "board"],
  overlaps: [],
};

const render = (kitchen: Kitchen) =>
  renderToString(<KitchenPlan kitchen={kitchen} ingredients={INGREDIENTS} />).replaceAll(
    "<!-- -->",
    "",
  );

test("los dos tiempos, con los que se decide, se leen con su nombre", () => {
  const html = renderToString(<KitchenTimes kitchen={KITCHEN} />).replaceAll("<!-- -->", "");

  expect(html).toContain("De principio a fin");
  expect(html).toContain("35 min");
  expect(html).toContain("Tú delante");
  expect(html).toContain("5 min");
});

test("la rejilla enseña cada ingrediente con su cantidad y lo que se hace con él", () => {
  const html = render(KITCHEN);

  expect(html).toContain("400 g");
  expect(html).toContain("Puerro");
  expect(html).toContain("Cocer a fuego lento");
  expect(html.toLowerCase()).toContain('rowspan="2"');
});

test("cada paso dice cuándo, con qué verbo y qué ingredientes entran", () => {
  const html = render(KITCHEN);

  expect(html).toContain("min 0 a 5");
  expect(html).toContain("Picar · 5 min · Puerro");
  expect(html).toContain("corre solo");
});

test("lo que la rejilla no puede dibujar se dice con palabras", () => {
  const incomplete = {
    ...KITCHEN,
    grid: { ...KITCHEN.grid, notes: ["no entra en ningún paso: Perejil"] },
  };

  expect(render(incomplete)).toContain("no entra en ningún paso: Perejil");
});

test("dos cosas pidiendo el mismo fuego se avisan con palabras", () => {
  const clashing = { ...KITCHEN, overlaps: [{ equipment: "hob", positions: [1, 2] }] };

  expect(render(clashing)).toContain("Los pasos 1 y 2 piden fuego a la vez");
});

test("una receta sin pasos lo dice, en vez de enseñar un diagrama vacío", () => {
  const empty = {
    ...KITCHEN,
    steps: [],
    lanes: [],
    total_minutes: 0,
    active_minutes: 0,
    grid: { ...KITCHEN.grid, cells: [], columns: 0 },
  };

  expect(render(empty)).toContain("todavía no tiene pasos");
});
