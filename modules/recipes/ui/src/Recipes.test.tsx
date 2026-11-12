import { renderToString } from "react-dom/server";

import { Empty, Grid, face, filtered, glyphOf, tagsByUse } from "./Recipes";
import type { Category, RecipeSummary } from "./api";

const CATEGORIES: Category[] = [
  { id: "vegetable", name: "Verdura", emoji: "🥬", position: 1 },
  { id: "fish", name: "Pescado y marisco", emoji: "🐟", position: 4 },
];

const RECIPES: RecipeSummary[] = [
  {
    id: "a1",
    name: "Porrusalda",
    servings: 4,
    version: 2,
    tags: ["invierno", "olla"],
    total_minutes: 55,
    active_minutes: 25,
    space_id: null,
    mine: true,
  },
  { id: "b2", name: "Tortilla", servings: 1, version: 1, tags: [], total_minutes: null, active_minutes: null, space_id: null, mine: true },
];

test("sin recetas se explica qué es una receta y con qué se agrupan los ingredientes", () => {
  const html = renderToString(<Empty categories={CATEGORIES} />);

  expect(html).toContain("Todavía no hay recetas");
  expect(html).toContain("🥬");
  expect(html).toContain("Verdura");
  expect(html).toContain("🐟");
});

test("cada receta abre su ficha y dice para cuánta gente es", () => {
  const html = renderToString(<Grid recipes={RECIPES} />).replaceAll("<!-- -->", "");

  expect(html).toContain('href="/recipes/receta/a1"');
  expect(html).toContain("Para 4 personas");
  expect(html).toContain("Para 1 persona<");
  expect(html).toContain(">invierno<");
  expect(html).toContain(">olla<");
});

test("la portada dice cuánto estás tú delante; una receta que se hace sola lo dice así, no con un cero", () => {
  expect(face({ total_minutes: 55, active_minutes: 25 })).toEqual({ figure: "25 min", caption: "tú delante" });
  expect(face({ total_minutes: 180, active_minutes: 0 })).toEqual({ figure: "sin faena", caption: "3 h en total" });
  expect(face({ total_minutes: 30, active_minutes: 30 })).toEqual({ figure: "30 min", caption: "en total" });
  expect(face({ total_minutes: null, active_minutes: null })).toEqual({});

  const html = renderToString(<Grid recipes={RECIPES} />).replaceAll("<!-- -->", "");
  expect(html).toContain("55 min en total");
  expect(html).not.toContain("0 min");
});

test("se busca sin tildes, por nombre o etiqueta, y se filtra por etiqueta", () => {
  expect(filtered(RECIPES, "PORRU", "").map((one) => one.name)).toEqual(["Porrusalda"]);
  expect(filtered(RECIPES, "olla", "").map((one) => one.name)).toEqual(["Porrusalda"]);
  expect(filtered(RECIPES, "", "invierno").map((one) => one.name)).toEqual(["Porrusalda"]);
  expect(filtered(RECIPES, "tortilla", "invierno")).toEqual([]);
  expect(tagsByUse([...RECIPES, { ...RECIPES[0]!, id: "c3", tags: ["olla"] }])).toEqual(["olla", "invierno"]);
});

test("el dibujo de la esquina sale de la etiqueta", () => {
  expect(glyphOf(["Desayuno"])).toBe("sun");
  expect(glyphOf(["carne", "cena"])).toBe("moon");
  expect(glyphOf([])).toBe("flame");
});
