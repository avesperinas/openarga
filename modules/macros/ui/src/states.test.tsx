// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { todayIso } from "./words";

const MEALS = [
  ["breakfast", "Desayuno", "08:30"],
  ["morning", "Media mañana", "11:00"],
  ["lunch", "Comida", "14:30"],
  ["snack", "Merienda", "18:00"],
  ["dinner", "Cena", "21:30"],
].map(([meal, label, usual_at]) => ({
  meal,
  label,
  usual_at,
  started: meal === "breakfast",
  current: meal === "breakfast",
  kcal: 0,
  protein: 0,
  entry_ids: [],
  planned_ids: [],
}));

const EMPTY_DAY = {
  day: todayIso(),
  nutrients: {},
  coverage: {},
  target: null,
  remaining: {},
  drinks: { caffeine_mg: null, alcohol_g: null, alcohol_units: null, water_l: 0 },
  entries: [],
  goals: [],
  day_kind: { day: todayIso(), kind: "rest", source: "none", workouts: [] },
  groups: [],
  caffeine: null,
  planned: [],
  meals: MEALS,
  complete: false,
};

const EMPTY_WEEK = {
  first: todayIso(),
  last: todayIso(),
  days_logged: 0,
  averages: {},
  days: [],
  micros: [],
  profile: { sex: null, age: null, from_health: false },
  drinks: { caffeine_mg: null, alcohol_g: null, alcohol_units: null, water_l: 0 },
  goals: [],
  compliance: [],
  expenditure: null,
};

type Reply = () => unknown;

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
  replies = {
    "GET /api/macros/day": () => EMPTY_DAY,
    "GET /api/macros/usual/breakfast": () => ({
      meal: "breakfast",
      label: "Desayuno",
      day: todayIso(),
      yesterday: [],
      usual: null,
      items: [],
      recent: [],
      menus: [],
    }),
    "GET /api/macros/recipes/outdated": () => [],
    "GET /api/macros/week": () => EMPTY_WEEK,
    "GET /api/macros/goals": () => ({ day_kind: EMPTY_DAY.day_kind, goals: [] }),
    "GET /api/macros/target": () => null,
    "GET /api/macros/references": () => ({ profile: EMPTY_WEEK.profile, references: [] }),
    "GET /api/macros/nutrients": () => [],
    "GET /api/macros/weight": () => ({ days: [], latest: null }),
    "GET /api/macros/templates": () => [],
    "GET /api/macros/settings": () => ({ protein_at: "20:00:00" }),
    "GET /api/macros/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
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

async function open(path = "/macros/") {
  window.history.replaceState(null, "", path);
  act(() => root.render(<App />));
  await settle();
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("hoy", () => {
  it("mientras llega, el esqueleto", async () => {
    replies["GET /api/macros/day"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("vacío, cada comida trae su Añadir y el de abajo lleva la de ahora", async () => {
    await open();
    expect(host.textContent).toContain("Desayuno");
    expect(host.textContent).toContain("Lo normal es contárselo a Claude");
    expect(button("Añadir")).toBeDefined();
    expect(Array.from(host.querySelectorAll(".create-button")).map((one) => one.textContent)).toEqual(["Desayuno"]);
  });

  it("si falla, lo dice y reintentar lo trae", async () => {
    replies["GET /api/macros/day"] = () => json({ detail: "la base no contesta" }, 503);
    await open();
    expect(host.textContent).toContain("Macros no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/macros/day"] = () => EMPTY_DAY;
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Lo normal es contárselo a Claude");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });
});

describe("la semana", () => {
  it("sin nada apuntado, el botón lleva a apuntar", async () => {
    await open("/macros/semana");
    expect(host.textContent).toContain("Nada apuntado esta semana");
    expect(button("Apuntar")).toBeDefined();
  });

  it("si falla, lo dice con reintentar", async () => {
    replies["GET /api/macros/week"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/macros/semana");
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("el objetivo", () => {
  it("si falla, lo dice con reintentar", async () => {
    replies["GET /api/macros/references"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/macros/objetivo");
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("los ajustes", () => {
  it("sin menús, dice cómo se crean", async () => {
    await open("/macros/ajustes");
    expect(host.textContent).toContain("Aún no hay menús");
  });
});

describe("axe-core sin errores graves", () => {
  it.each(["/macros/", "/macros/semana", "/macros/objetivo", "/macros/ajustes"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
