import { renderToString } from "react-dom/server";

import { inLocale } from "./i18n/testing";
import { KitchenPlan, KitchenTimes } from "./Kitchen";
import type { Ingredient, Kitchen } from "./api";

const INGREDIENTS: Ingredient[] = [
  { position: 1, name: "Leek", food_id: "f1", category_id: "vegetable", quantity: 400, unit: "g", note: null, optional: false, grams: 400 },
  { position: 2, name: "Potato", food_id: "f2", category_id: "vegetable", quantity: 600, unit: "g", note: null, optional: false, grams: 600 },
];

const KITCHEN: Kitchen = {
  steps: [
    { position: 1, action: "chop", text: "Chop the leek", minutes: 5, attended: true, equipment: "board", ingredients: ["Leek"], uses: [1], after: [], start: 0, end: 5 },
    { position: 2, action: "simmer", text: "Simmer gently", minutes: 30, attended: false, equipment: "hob", ingredients: ["Potato"], uses: [2], after: [1], start: 5, end: 35 },
  ],
  grid: {
    rows: [
      { position: 1, name: "Leek", orphan: false },
      { position: 2, name: "Potato", orphan: false },
    ],
    cells: [
      { position: 1, action: "chop", text: "Chop the leek", minutes: 5, attended: true, equipment: "board", column: 1, row: 1, span: 1 },
      { position: 2, action: "simmer", text: "Simmer gently", minutes: 30, attended: false, equipment: "hob", column: 2, row: 1, span: 2 },
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
  renderToString(inLocale(<KitchenPlan kitchen={kitchen} ingredients={INGREDIENTS} />)).replaceAll(
    "<!-- -->",
    "",
  );

test("the two times you decide with read with their names", () => {
  const html = renderToString(inLocale(<KitchenTimes kitchen={KITCHEN} />)).replaceAll("<!-- -->", "");

  expect(html).toContain("Start to finish");
  expect(html).toContain("35 min");
  expect(html).toContain("You there");
  expect(html).toContain("5 min");
});

test("the grid shows each ingredient with its quantity and what is done with it", () => {
  const html = render(KITCHEN);

  expect(html).toContain("400 g");
  expect(html).toContain("Leek");
  expect(html).toContain("Simmer gently");
  expect(html.toLowerCase()).toContain('rowspan="2"');
});

test("each step says when, with which verb and which ingredients go in", () => {
  const html = render(KITCHEN);

  expect(html).toContain("min 0 to 5");
  expect(html).toContain("Chop · 5 min · Leek");
  expect(html).toContain("runs by itself");
});

test("what the grid cannot draw is said in words", () => {
  const incomplete = {
    ...KITCHEN,
    grid: { ...KITCHEN.grid, notes: ["goes into no step: Parsley"] },
  };

  expect(render(incomplete)).toContain("goes into no step: Parsley");
});

test("two things asking for the same hob are flagged in words", () => {
  const clashing = { ...KITCHEN, overlaps: [{ equipment: "hob", positions: [1, 2] }] };

  expect(render(clashing)).toContain("Steps 1 and 2 need the hob at the same time");
});

test("a recipe without steps says so instead of showing an empty diagram", () => {
  const empty = {
    ...KITCHEN,
    steps: [],
    lanes: [],
    total_minutes: 0,
    active_minutes: 0,
    grid: { ...KITCHEN.grid, cells: [], columns: 0 },
  };

  expect(render(empty)).toContain("has no steps yet");
});
