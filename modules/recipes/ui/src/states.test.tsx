// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Category, Food, RecipeSummary } from "./api";
import { App } from "./App";

const FRUIT: Category = { id: "fruit", name: "Fruta", emoji: "🍌", position: 1 };

const food = (id: string, name: string): Food => ({
  id,
  name,
  alias: null,
  source: "manual",
  source_ref: null,
  category_id: "fruit",
  macros: { kcal: 89, protein: 1.1, fat: 0.3, carbs: 22.8, fiber: 2.6, salt: 0 },
  density_g_ml: null,
  grams_per_unit: null,
  corrected: false,
});

const FOODS = [food("a", "Pl\u00e1tano shake"), food("b", "Pl\u00e1tano"), food("c", "Kiwi")];

const LEEK_SOUP: RecipeSummary = {
  id: "0a0a0a0a-0000-4000-8000-00000000a0a0",
  name: "Leek soup",
  servings: 4,
  version: 1,
  tags: [],
  total_minutes: 40,
  active_minutes: 10,
  space_id: null,
  mine: true,
};

type Reply = () => unknown;
let asked: string[] = [];

let root: Root;
let host: HTMLElement;
let replies: Record<string, Reply>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }) as never;
});

beforeEach(() => {
  void reset();
  asked = [];
  replies = {
    "GET /api/recipes/recipes": () => [LEEK_SOUP],
    "GET /api/recipes/categories": () => [FRUIT],
    "GET /api/recipes/foods": () => FOODS,
    "GET /api/recipes/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url}`);
      const reply = replies[`${init?.method ?? "GET"} ${url}`];
      if (!reply) return json({ detail: "no existe" }, 404);
      const body = await reply();
      return body instanceof Response ? body : json(body);
    }),
  );
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/recipes/") {
  window.history.replaceState(null, "", path);
  act(() => root.render(<App />));
  await settle();
}

function type(value: string) {
  const input = host.querySelector<HTMLInputElement>("input[type=search]")!;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("the recipe book", () => {
  it("while it loads, the skeleton", async () => {
    replies["GET /api/recipes/recipes"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("empty, the button writes the first one", async () => {
    replies["GET /api/recipes/recipes"] = () => [];
    await open();
    act(() => button("Escribir la primera")!.click());
    await settle();
    expect(window.location.pathname).toBe("/recipes/new");
  });

  it("if it fails, it says so and retrying brings it", async () => {
    replies["GET /api/recipes/recipes"] = () => json({ detail: "the database is not answering" }, 503);
    await open();
    expect(host.textContent).toContain("No se pudo leer el recetario");

    replies["GET /api/recipes/recipes"] = () => [LEEK_SOUP];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Leek soup");
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });

  it("axe-core without serious errors", async () => {
    await open();
    expect(await serious()).toEqual([]);
  });
});

describe("the pantry", () => {
  it("it searches without accents, and what starts the same comes first", async () => {
    await open("/recipes/pantry");
    type("platano");
    await settle();

    const text = host.textContent ?? "";
    expect(text).toContain("En tu despensa2");
    expect(text).toContain("Pl\u00e1tano");
    expect(text.indexOf("Pl\u00e1tano")).toBeLessThan(text.indexOf("Batido de plátano"));
    expect(text).not.toContain("Kiwi");
  });

  it("empty, it offers to create one by hand", async () => {
    replies["GET /api/recipes/foods"] = () => [];
    await open("/recipes/pantry");
    expect(host.textContent).toContain("La despensa está vacía");
    expect(button("Crear uno a mano")).toBeDefined();
  });

  it("if it fails, retry", async () => {
    replies["GET /api/recipes/foods"] = () => json({ detail: "no" }, 500);
    await open("/recipes/pantry");
    expect(host.textContent).toContain("No se pudo leer la despensa");

    replies["GET /api/recipes/foods"] = () => FOODS;
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Kiwi");
  });

  it.each(["/recipes/pantry", "/recipes/ajustes"])("%s, axe-core sin errores graves", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});

describe("a recipe", () => {
  it("if it cannot be read, retry", async () => {
    const path = `/api/recipes/recipes/${LEEK_SOUP.id}`;
    replies[`GET ${path}`] = () => json({ detail: "no" }, 500);
    await open(`/recipes/recipe/${LEEK_SOUP.id}`);
    expect(host.textContent).toContain("No se pudo leer la receta");
    expect(button("Reintentar")).toBeDefined();
  });

  it("the editor does not show the form until it has the recipe", async () => {
    const path = `/api/recipes/recipes/${LEEK_SOUP.id}`;
    replies[`GET ${path}`] = () => json({ detail: "no" }, 500);
    await open(`/recipes/recipe/${LEEK_SOUP.id}/edit`);
    expect(host.querySelector("input[type=text], input:not([type])")).toBeNull();
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("after changing a food", () => {
  it("the recipe book is read again: its macros or name change the recipes", async () => {
    replies["PUT /api/recipes/foods/c/alias"] = () => ({ ...FOODS[2]!, alias: "Kiwi verde" });
    await open();
    act(() => root.unmount());
    root = createRoot(host);
    await open("/recipes/pantry");

    const row = Array.from(host.querySelectorAll<HTMLElement>("button, [role=button]")).find((one) =>
      one.textContent?.includes("Kiwi"),
    )!;
    act(() => row.click());
    await settle();
    const save = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(
      (one) => one.textContent === "Guardar",
    )!;
    act(() => save.click());
    await settle();

    act(() => root.unmount());
    root = createRoot(host);
    await open();
    expect(asked.filter((one) => one === "GET /api/recipes/recipes")).toHaveLength(2);
  });
});
