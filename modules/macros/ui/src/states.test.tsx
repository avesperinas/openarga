// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { english, inLocale } from "./i18n/testing";
import { todayIso } from "./words";

const MEALS = [
  ["breakfast", "Breakfast", "08:30"],
  ["morning", "Mid-morning", "11:00"],
  ["lunch", "Lunch", "14:30"],
  ["snack", "Afternoon snack", "18:00"],
  ["dinner", "Dinner", "21:30"],
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
      label: "Breakfast",
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
      if (!reply) return json({ detail: "not found" }, 404);
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

const retry = () => host.querySelector<HTMLButtonElement>(".empty-state button");

async function open(path = "/macros/") {
  window.history.replaceState(null, "", path);
  act(() => root.render(inLocale(<App />)));
  await settle();
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("today", () => {
  it("while it loads, the skeleton", async () => {
    replies["GET /api/macros/day"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("empty, each meal has its Add and the one below carries the current meal", async () => {
    await open();
    expect(host.textContent).toContain("Breakfast");
    expect(host.textContent).toContain(english("day.tell_assistant"));
    expect(button(english("common.add"))).toBeDefined();
    expect(Array.from(host.querySelectorAll(".create-button")).map((one) => one.textContent)).toEqual(["Breakfast"]);
  });

  it("if it fails, it says so and retrying brings it", async () => {
    replies["GET /api/macros/day"] = () => json({ detail: "the database is not answering" }, 503);
    await open();
    expect(host.textContent).toContain(english("common.not_answering"));
    expect(host.textContent).toContain("the database is not answering");

    replies["GET /api/macros/day"] = () => EMPTY_DAY;
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain(english("day.tell_assistant"));
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.querySelector('.notice[data-tone="warning"]')).not.toBeNull();
  });
});

describe("the week", () => {
  it("with nothing logged, the button goes to logging", async () => {
    await open("/macros/week");
    expect(host.textContent).toContain(english("week.empty"));
    expect(button(english("common.log"))).toBeDefined();
  });

  it("if it fails, it says so with a retry", async () => {
    replies["GET /api/macros/week"] = () => json({ detail: "the database is not answering" }, 503);
    await open("/macros/week");
    expect(host.textContent).toContain("the database is not answering");
    expect(retry()).not.toBeNull();
  });
});

describe("the target", () => {
  it("if it fails, it says so with a retry", async () => {
    replies["GET /api/macros/references"] = () => json({ detail: "the database is not answering" }, 503);
    await open("/macros/goals");
    expect(host.textContent).toContain("the database is not answering");
    expect(retry()).not.toBeNull();
  });
});

describe("the settings", () => {
  it("without menus, it says how to create them", async () => {
    await open("/macros/settings");
    expect(host.textContent).toContain(english("menu.none"));
  });
});

describe("axe-core without serious errors", () => {
  it.each(["/macros/", "/macros/week", "/macros/goals", "/macros/settings"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
