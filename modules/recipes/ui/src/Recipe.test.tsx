import { configureRegional } from "@openarga/ui";
import { renderToString } from "react-dom/server";

import { english as t, inLocale } from "./i18n/testing";
import { Macros, deleteConsequence, ingredientDetail, kcalSplit, microRows } from "./Recipe";
import type { NutrientInfo, Recipe } from "./api";

beforeEach(() => configureRegional({ locale: "en-US" }));
afterEach(() => configureRegional({ locale: "es-ES" }));

const BASE: Recipe = {
  id: "r1",
  name: "Leek soup",
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

test("the figure you look at is per serving, with the total below", () => {
  const html = renderToString(inLocale(<Macros recipe={BASE} />)).replaceAll("<!-- -->", "");

  expect(html).toContain("Per serving");
  expect(html).toContain("<dd>279</dd>");
  expect(html).toContain("<dd>7.3</dd>");
  expect(html).toContain('data-count="4"');
  expect(html).toContain("Whole recipe (4 servings): 1,114 kcal");
});

test("an incomplete figure says what it lacks, with names", () => {
  const incomplete = {
    ...BASE,
    nutrition: {
      ...BASE.nutrition,
      counted: 3,
      ingredients: 4,
      uncertainty: "1 of 4 ingredients missing (homemade sofrito)",
    },
  };

  const html = renderToString(inLocale(<Macros recipe={incomplete} />));

  expect(html).toContain("1 of 4 ingredients missing (homemade sofrito)");
});

test("a macro nobody declares shows as a gap and not as zero", () => {
  const html = renderToString(inLocale(<Macros recipe={BASE} />)).replaceAll("<!-- -->", "");

  expect(html).not.toContain("0 g fibre");
});

test("deleting says what is lost: its ingredients and, if any, its versions", () => {
  const group = (ingredients: number) => ({ ingredients: Array.from({ length: ingredients }) }) as unknown as Recipe["groups"][number];

  expect(deleteConsequence({ versions: 1, groups: [group(2)] }, t)).toBe("It is deleted with its 2 ingredients. This cannot be undone.");
  expect(deleteConsequence({ versions: 3, groups: [group(1)] }, t)).toBe(
    "It is deleted with its ingredient and its 3 versions. This cannot be undone.",
  );
  expect(deleteConsequence({ versions: 1, groups: [] }, t)).toBe("It is deleted. This cannot be undone.");
});

const LIST: NutrientInfo[] = [
  { key: "kcal", name: "Energy", unit: "kcal", group: "energy", front: true, digits: 0 },
  { key: "iron", name: "Iron", unit: "mg", group: "mineral", front: true, digits: 1 },
  { key: "vitamin_d", name: "Vitamin D", unit: "µg", group: "vitamin", front: true, digits: 1 },
  { key: "folate", name: "Folate", unit: "µg", group: "vitamin", front: true, digits: 0 },
  { key: "selenium", name: "Selenium", unit: "µg", group: "mineral", front: false, digits: 1 },
];

describe("micros per serving", () => {
  it("shows the front-page ones the recipe has, without macros nor the see-all ones", () => {
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

  it("without nutrients from an earlier version, it shows nothing", () => {
    expect(microRows(BASE, LIST)).toEqual([]);
  });
});

test("where the kcal come from: 4 per gram of protein and carbs and 9 of fat", () => {
  const split = kcalSplit({ protein: 25, fat: 10, carbs: 50 }, t);
  expect(split.map((part) => [part.label, part.value])).toEqual([
    ["Protein", "26 %"],
    ["Fat", "23 %"],
    ["Carbs", "51 %"],
  ]);
  expect(kcalSplit({ protein: 0, fat: 0, carbs: 0 }, t).map((part) => part.value)).toEqual(["–", "–", "–"]);
});

test("an ingredient says how much, its note, whether optional and whether it adds no macros", () => {
  expect(ingredientDetail({ quantity: 2, unit: "unit", note: "diced", optional: false, food_id: "f" }, t)).toBe("2 u · diced");
  expect(ingredientDetail({ quantity: 1, unit: "pinch", note: null, optional: true, food_id: null }, t)).toBe(
    "1 pinch · optional · no macros",
  );
});
