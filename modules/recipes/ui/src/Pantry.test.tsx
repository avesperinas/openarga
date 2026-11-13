import { configureRegional } from "@openarga/ui";
import { renderToString } from "react-dom/server";

import { english as t, inLocale } from "./i18n/testing";
import { FoodSheet, Outside, foodDetails, groupByCategory, matches, perLabel, replacements } from "./Pantry";
import type { Candidate, Category, Food, SearchOut } from "./api";

beforeEach(() => configureRegional({ locale: "en-US" }));
afterEach(() => configureRegional({ locale: "es-ES" }));

const CATEGORIES: Category[] = [
  { id: "vegetable", name: "Vegetables", emoji: "🥬", position: 1 },
  { id: "dairy", name: "Dairy and eggs", emoji: "🧀", position: 5 },
  { id: "fish", name: "Fish and seafood", emoji: "🐟", position: 4 },
];

const macros = { kcal: 61, protein: 1.5, fat: 0.3, carbs: 14.15, fiber: null, salt: null };

function food(id: string, name: string, category_id: string): Food {
  return {
    id,
    name,
    alias: null,
    source: "usda",
    source_ref: id,
    category_id,
    macros,
    density_g_ml: null,
    grams_per_unit: null,
    corrected: false,
  };
}

test("the pantry groups by category, in catalogue order and without empty ones", () => {
  const grouped = groupByCategory(
    [food("1", "Leek", "vegetable"), food("2", "Yogur", "dairy"), food("3", "Onion", "vegetable")],
    CATEGORIES,
  );

  expect(grouped.map(({ category }) => category.id)).toEqual(["vegetable", "dairy"]);
  expect(grouped[0]?.items.map((one) => one.name)).toEqual(["Onion", "Leek"]);
});

test("within each category what you call it wins, not what the source calls it", () => {
  const grouped = groupByCategory(
    [
      { ...food("1", "Onions, raw", "vegetable"), alias: "Onion" },
      { ...food("2", "Garlic, raw", "vegetable"), alias: "Garlic" },
      food("3", "Beets, raw", "vegetable"),
    ],
    CATEGORIES,
  );

  expect(grouped[0]?.items.map((one) => one.id)).toEqual(["2", "3", "1"]);
});

test("a food is found by its alias and by its source's name", () => {
  const onion = { ...food("1", "Onions, raw", "vegetable"), alias: "Onion" };

  expect(matches(onion, "cebo")).toBe(true);
  expect(matches(onion, "onion")).toBe(true);
  expect(matches(onion, "ajo")).toBe(false);
});

test("a food's card shows your alias and where it came from", () => {
  const onion = { ...food("1", "Onions, raw", "vegetable"), alias: "Onion" };

  const html = renderToString(
    inLocale(<FoodSheet food={onion} onClose={() => undefined} onSaved={() => undefined} />),
  ).replaceAll("<!-- -->", "");

  expect(html).toContain("Onion");
  expect(html).toContain("USDA: “Onions, raw”");
});

const CANDIDATE: Candidate = {
  source: "usda",
  source_ref: "11246",
  name: "Leeks, raw",
  brand: null,
  macros,
  category_hint: "vegetable",
  known_id: null,
};

test("a candidate says where it comes from and what macros it has", () => {
  const found: SearchOut = { candidates: [CANDIDATE], failed: [] };

  const html = renderToString(inLocale(<Outside found={found} onAdd={() => undefined} />)).replaceAll("<!-- -->", "");

  expect(html).toContain("Leeks, raw");
  expect(html).toContain("61 kcal · 1.5 P · 0.3 F · 14.2 C · USDA");
});

test("what you already have is marked, so you do not add it again thinking it is new", () => {
  const found: SearchOut = { candidates: [{ ...CANDIDATE, known_id: "abc" }], failed: [] };

  const html = renderToString(inLocale(<Outside found={found} onAdd={() => undefined} />)).replaceAll("<!-- -->", "");

  expect(html).toContain("you already have it");
});

test("a source that did not answer is said, with its reason", () => {
  const found: SearchOut = {
    candidates: [CANDIDATE],
    failed: [{ source: "usda", reason: "no USDA_API_KEY: only Open Food Facts is searched" }],
  };

  const html = renderToString(inLocale(<Outside found={found} onAdd={() => undefined} />));

  expect(html).toContain("no USDA_API_KEY");
});

test("a candidate with impossible figures is set aside and named", () => {
  const found: SearchOut = {
    candidates: [CANDIDATE],
    failed: [],
    discarded: [{ source: "off", name: "Synthetic coffee", reason: "3210 g of salt per 100 g" }],
  };

  const html = renderToString(inLocale(<Outside found={found} onAdd={() => undefined} />));

  expect(html).toContain("Synthetic coffee (3210 g of salt per 100 g)");
});

test("without candidates the way out is offered instead of a silent screen", () => {
  const html = renderToString(inLocale(<Outside found={{ candidates: [], failed: [] }} onAdd={() => undefined} />));

  expect(html).toContain("You can create it by hand");
});

test("the card says where the figures come from, its measures and what is eaten", () => {
  const food = {
    id: "f1",
    name: "Bonito",
    alias: null,
    source: "manual",
    source_ref: null,
    category_id: "fish",
    macros: { kcal: 140, protein: 24, fat: 5, carbs: 0, fiber: null, salt: null },
    density_g_ml: null,
    grams_per_unit: null,
    corrected: true,
    provenance: "estimated by the model",
    micros_from: "f2",
    micros_from_label: "Generic tuna",
    borrowed: ["vitamin_d", "omega3_epa"],
    edible_fraction: 0.82,
    portions: [{ name: "steak", grams: 600 }],
  } as Food;

  expect(foodDetails(food, t)).toEqual([
    "Figures from: estimated by the model.",
    "2 nutrients borrowed from “Generic tuna”.",
    "Measures: steak, 600 g.",
    "82 % of what is weighed whole is eaten.",
  ]);
});

test("a supplement gives its figures per unit", () => {
  const capsule = { nutrients_per: "unit", unit_name: "capsule" } as Food;
  const plain = { nutrients_per: "100g", unit_name: null } as Food;

  expect(perLabel(capsule, t)).toBe("capsule");
  expect(perLabel(plain, t)).toBe("100 g");
});

test("it is replaced by another pantry food measured alike, never by itself", () => {
  const milk = { id: "a", name: "Milk", alias: null, nutrients_per: "100g" } as Food;
  const other = { id: "b", name: "Whole milk", alias: null, nutrients_per: "100g" } as Food;
  const capsule = { id: "c", name: "Omega 3", alias: null, nutrients_per: "unit" } as Food;

  expect(replacements(milk, [milk, capsule, other]).map((one) => one.id)).toEqual(["b"]);
});
