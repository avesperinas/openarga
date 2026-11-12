import { renderToString } from "react-dom/server";

import { FoodSheet, Outside, foodDetails, groupByCategory, matches, perLabel, replacements } from "./Pantry";
import type { Candidate, Category, Food, SearchOut } from "./api";

const CATEGORIES: Category[] = [
  { id: "vegetable", name: "Verdura", emoji: "🥬", position: 1 },
  { id: "dairy", name: "Lácteos y huevos", emoji: "🧀", position: 5 },
  { id: "fish", name: "Pescado y marisco", emoji: "🐟", position: 4 },
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

test("la despensa se agrupa por categoría, en el orden del catálogo y sin las vacías", () => {
  const grouped = groupByCategory(
    [food("1", "Puerro", "vegetable"), food("2", "Yogur", "dairy"), food("3", "Cebolla", "vegetable")],
    CATEGORIES,
  );

  expect(grouped.map(({ category }) => category.id)).toEqual(["vegetable", "dairy"]);
  expect(grouped[0]?.items.map((one) => one.name)).toEqual(["Cebolla", "Puerro"]);
});

test("dentro de cada categoría manda cómo lo llamas tú, no cómo lo llama la fuente", () => {
  const grouped = groupByCategory(
    [
      { ...food("1", "Onions, raw", "vegetable"), alias: "Cebolla" },
      { ...food("2", "Garlic, raw", "vegetable"), alias: "Ajo" },
      food("3", "Beets, raw", "vegetable"),
    ],
    CATEGORIES,
  );

  expect(grouped[0]?.items.map((one) => one.id)).toEqual(["2", "3", "1"]);
});

test("un alimento se busca por su alias y por el nombre de su fuente", () => {
  const onion = { ...food("1", "Onions, raw", "vegetable"), alias: "Cebolla" };

  expect(matches(onion, "cebo")).toBe(true);
  expect(matches(onion, "onion")).toBe(true);
  expect(matches(onion, "ajo")).toBe(false);
});

test("la ficha de un alimento enseña tu alias y deja a la vista de dónde vino", () => {
  const onion = { ...food("1", "Onions, raw", "vegetable"), alias: "Cebolla" };

  const html = renderToString(
    <FoodSheet food={onion} onClose={() => undefined} onSaved={() => undefined} />,
  ).replaceAll("<!-- -->", "");

  expect(html).toContain("Cebolla");
  expect(html).toContain("USDA: «Onions, raw»");
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

test("un candidato dice de dónde sale y qué macros trae", () => {
  const found: SearchOut = { candidates: [CANDIDATE], failed: [] };

  const html = renderToString(<Outside found={found} onAdd={() => undefined} />).replaceAll("<!-- -->", "");

  expect(html).toContain("Leeks, raw");
  expect(html).toContain("61 kcal · 1,5 P · 0,3 G · 14,2 H · USDA");
});

test("lo que ya tienes se marca, para no volver a añadirlo creyendo que es nuevo", () => {
  const found: SearchOut = { candidates: [{ ...CANDIDATE, known_id: "abc" }], failed: [] };

  const html = renderToString(<Outside found={found} onAdd={() => undefined} />).replaceAll("<!-- -->", "");

  expect(html).toContain("ya la tienes");
});

test("una fuente que no contestó se dice, con su motivo", () => {
  const found: SearchOut = {
    candidates: [CANDIDATE],
    failed: [{ source: "usda", reason: "sin USDA_API_KEY: solo se busca en OpenFoodFacts" }],
  };

  const html = renderToString(<Outside found={found} onAdd={() => undefined} />);

  expect(html).toContain("sin USDA_API_KEY");
});

test("un candidato con cifras imposibles se aparta y se dice cuál", () => {
  const found: SearchOut = {
    candidates: [CANDIDATE],
    failed: [],
    discarded: [{ source: "off", name: "Café sintético", reason: "3210 g de sal por 100 g" }],
  };

  const html = renderToString(<Outside found={found} onAdd={() => undefined} />);

  expect(html).toContain("Café sintético (3210 g de sal por 100 g)");
});

test("sin candidatos se ofrece la salida, en vez de dejar la pantalla muda", () => {
  const html = renderToString(<Outside found={{ candidates: [], failed: [] }} onAdd={() => undefined} />);

  expect(html).toContain("Puedes crearlo a mano");
});

test("la ficha dice de dónde salen las cifras, sus medidas y lo que se come", () => {
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
    provenance: "estimado por el modelo",
    micros_from: "f2",
    micros_from_label: "Atún genérico",
    borrowed: ["vitamin_d", "omega3_epa"],
    edible_fraction: 0.82,
    portions: [{ name: "rueda", grams: 600 }],
  } as Food;

  expect(foodDetails(food)).toEqual([
    "Cifras de: estimado por el modelo.",
    "2 nutrientes prestados de «Atún genérico».",
    "Medidas: rueda, 600 g.",
    "Se come el 82 % de lo que se pesa entero.",
  ]);
});

test("un suplemento dice sus cifras por unidad", () => {
  const capsule = { nutrients_per: "unit", unit_name: "cápsula" } as Food;
  const plain = { nutrients_per: "100g", unit_name: null } as Food;

  expect(perLabel(capsule)).toBe("cápsula");
  expect(perLabel(plain)).toBe("100 g");
});

test("se sustituye por otro de la despensa que vaya igual, nunca por sí mismo", () => {
  const milk = { id: "a", name: "Leche", alias: null, nutrients_per: "100g" } as Food;
  const other = { id: "b", name: "Leche entera", alias: null, nutrients_per: "100g" } as Food;
  const capsule = { id: "c", name: "Omega 3", alias: null, nutrients_per: "unit" } as Food;

  expect(replacements(milk, [milk, capsule, other]).map((one) => one.id)).toEqual(["b"]);
});
