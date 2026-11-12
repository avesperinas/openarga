import { renderToString } from "react-dom/server";

import { Macros, deleteConsequence, ingredientDetail, kcalSplit, microRows } from "./Recipe";
import type { NutrientInfo, Recipe } from "./api";

const BASE: Recipe = {
  id: "r1",
  name: "Porrusalda",
  servings: 4,
  requested_servings: 4,
  space_id: null,
  mine: true,
  version: 1,
  versions: 1,
  source: "app",
  note: null,
  tags: [],
  groups: [],
  kitchen: { steps: [], grid: { rows: [], cells: [], bands: [], columns: 0, notes: [] }, total_minutes: 0, active_minutes: 0, lanes: [], overlaps: [] },
  nutrition: {
    total: { kcal: 1114.4, protein: 52.1, fat: 29.3, carbs: 161.6, fiber: null, salt: null },
    per_serving: { kcal: 278.6, protein: 13, fat: 7.3, carbs: 40.4, fiber: null, salt: null },
    counted: 4,
    ingredients: 4,
    uncertainty: null,
  },
};

test("la cifra que se mira es la de la ración, y el total va debajo", () => {
  const html = renderToString(<Macros recipe={BASE} />).replaceAll("<!-- -->", "");

  expect(html).toContain("Por ración");
  expect(html).toContain("<dd>279</dd>");
  expect(html).toContain("<dd>7,3</dd>");
  expect(html).toContain('data-count="4"');
  expect(html).toContain("Receta entera (4 raciones): 1.114 kcal");
});

test("una cifra incompleta lleva dicho qué le falta, con nombres", () => {
  const incomplete = {
    ...BASE,
    nutrition: {
      ...BASE.nutrition,
      counted: 3,
      ingredients: 4,
      uncertainty: "falta 1 de 4 ingredientes (Sofrito de la abuela)",
    },
  };

  const html = renderToString(<Macros recipe={incomplete} />);

  expect(html).toContain("falta 1 de 4 ingredientes (Sofrito de la abuela)");
});

test("una macro que nadie declara sale como hueco y no como cero", () => {
  const html = renderToString(<Macros recipe={BASE} />).replaceAll("<!-- -->", "");

  expect(html).not.toContain("0 g fibra");
});

test("al borrar se dice qué se pierde: sus ingredientes y, si las hay, sus versiones", () => {
  const group = (ingredients: number) => ({ ingredients: Array.from({ length: ingredients }) }) as unknown as Recipe["groups"][number];

  expect(deleteConsequence({ versions: 1, groups: [group(2)] })).toBe("Se borra con sus 2 ingredientes. No se puede deshacer.");
  expect(deleteConsequence({ versions: 3, groups: [group(1)] })).toBe(
    "Se borra con su ingrediente y sus 3 versiones. No se puede deshacer.",
  );
  expect(deleteConsequence({ versions: 1, groups: [] })).toBe("Se borra. No se puede deshacer.");
});

const LIST: NutrientInfo[] = [
  { key: "kcal", name: "Energía", unit: "kcal", group: "energy", front: true, digits: 0 },
  { key: "iron", name: "Hierro", unit: "mg", group: "mineral", front: true, digits: 1 },
  { key: "vitamin_d", name: "Vitamina D", unit: "µg", group: "vitamin", front: true, digits: 1 },
  { key: "folate", name: "Folato", unit: "µg", group: "vitamin", front: true, digits: 0 },
  { key: "selenium", name: "Selenio", unit: "µg", group: "mineral", front: false, digits: 1 },
];

describe("los micros por ración", () => {
  it("enseña los de portada que la receta tiene, sin macros ni los de «ver todos»", () => {
    const recipe = {
      nutrition: {
        ...BASE.nutrition,
        nutrients: { kcal: 300, iron: 6.5, folate: 479, selenium: 3 },
        coverage: { kcal: 1, iron: 0.78, folate: 1, selenium: 1 },
      },
    };
    const rows = microRows(recipe, LIST);
    expect(rows.map((row) => [row.info.key, row.value, row.partial])).toEqual([
      ["iron", 6.5, true],
      ["folate", 479, false],
    ]);
  });

  it("sin nutrientes de una versión anterior, no enseña nada", () => {
    expect(microRows(BASE, LIST)).toEqual([]);
  });
});

test("de dónde salen las kcal: 4 por gramo de proteína e hidratos y 9 de grasa", () => {
  const split = kcalSplit({ protein: 25, fat: 10, carbs: 50 });
  expect(split.map((part) => [part.label, part.value])).toEqual([
    ["Proteína", "26 %"],
    ["Grasa", "23 %"],
    ["Hidratos", "51 %"],
  ]);
  expect(kcalSplit({ protein: 0, fat: 0, carbs: 0 }).map((part) => part.value)).toEqual(["–", "–", "–"]);
});

test("un ingrediente dice cuánto, su nota, si es opcional y si no suma macros", () => {
  expect(ingredientDetail({ quantity: 2, unit: "unit", note: "en daditos", optional: false, food_id: "f" })).toBe("2 ud · en daditos");
  expect(ingredientDetail({ quantity: 1, unit: "pinch", note: null, optional: true, food_id: null })).toBe(
    "1 pizca · opcional · sin macros",
  );
});
