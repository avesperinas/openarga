import { renderToString } from "react-dom/server";

import { english as t, inLocale } from "./i18n/testing";
import { Empty, Grid, face, filtered, glyphOf, tagsByUse } from "./Recipes";
import type { Category, RecipeSummary } from "./api";

const CATEGORIES: Category[] = [
  { id: "vegetable", name: "Vegetables", emoji: "🥬", position: 1 },
  { id: "fish", name: "Fish and seafood", emoji: "🐟", position: 4 },
];

const RECIPES: RecipeSummary[] = [
  {
    id: "a1",
    name: "Leek soup",
    servings: 4,
    version: 2,
    tags: ["winter", "pot"],
    total_minutes: 55,
    active_minutes: 25,
    space_id: null,
    mine: true,
  },
  { id: "b2", name: "Omelette", servings: 1, version: 1, tags: [], total_minutes: null, active_minutes: null, space_id: null, mine: true },
];

test("without recipes it explains what a recipe is and how ingredients are grouped", () => {
  const html = renderToString(inLocale(<Empty categories={CATEGORIES} />));

  expect(html).toContain("No recipes yet");
  expect(html).toContain("🥬");
  expect(html).toContain("Vegetables");
  expect(html).toContain("🐟");
});

test("each recipe opens its card and says how many people it serves", () => {
  const html = renderToString(inLocale(<Grid recipes={RECIPES} />)).replaceAll("<!-- -->", "");

  expect(html).toContain('href="/recipes/recipe/a1"');
  expect(html).toContain("For 4 people");
  expect(html).toContain("For 1 person<");
  expect(html).toContain(">winter<");
  expect(html).toContain(">pot<");
});

test("the tile says how long you are there; a recipe that makes itself says so, not with a zero", () => {
  expect(face({ total_minutes: 55, active_minutes: 25 }, t)).toEqual({ figure: "25 min", caption: "you there" });
  expect(face({ total_minutes: 180, active_minutes: 0 }, t)).toEqual({ figure: "no work", caption: "3 h in all" });
  expect(face({ total_minutes: 30, active_minutes: 30 }, t)).toEqual({ figure: "30 min", caption: "in all" });
  expect(face({ total_minutes: null, active_minutes: null }, t)).toEqual({});

  const html = renderToString(inLocale(<Grid recipes={RECIPES} />)).replaceAll("<!-- -->", "");
  expect(html).toContain("55 min in all");
  expect(html).not.toContain("0 min");
});

test("it searches without accents, by name or tag, and filters by tag", () => {
  expect(filtered(RECIPES, "LEEK S", "").map((one) => one.name)).toEqual(["Leek soup"]);
  expect(filtered(RECIPES, "pot", "").map((one) => one.name)).toEqual(["Leek soup"]);
  expect(filtered(RECIPES, "", "winter").map((one) => one.name)).toEqual(["Leek soup"]);
  expect(filtered(RECIPES, "tortilla", "winter")).toEqual([]);
  expect(tagsByUse([...RECIPES, { ...RECIPES[0]!, id: "c3", tags: ["pot"] }])).toEqual(["pot", "winter"]);
});

test("the corner drawing comes from the tag", () => {
  expect(glyphOf(["Breakfast"])).toBe("sun");
  expect(glyphOf(["meat", "dinner"])).toBe("moon");
  expect(glyphOf([])).toBe("flame");
});
