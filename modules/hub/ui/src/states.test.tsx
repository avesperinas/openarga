// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const CONNECTION = "0b7c2f1e-1b1a-4c55-9d1e-8a6f4a3c2b10";

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
    "GET /api/hub/catalogue": () => [
      {
        id: "calendar",
        name: "Calendarios",
        providers: [
          { id: "ical", name: "Calendario iCal", description: "", capabilities: ["sync"], available: true, single: false, lives_in: null, secrets: [] },
        ],
      },
    ],
    "GET /api/hub/connections": () => [],
    "GET /api/hub/apps": () => ({
      apps: [{ module: "planner", name: "Planner", view: "/planner", inlets: [{ key: "calendar", title: "Calendarios", providers: ["ical"] }], services: [] }],
      others: [],
    }),
    "GET /api/hub/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
      if (!reply) return json({ detail: "esa conexión no existe" }, 404);
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

async function open(path = "/hub/") {
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

describe("la portada", () => {
  it("mientras llega, el esqueleto", async () => {
    replies["GET /api/hub/connections"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("sin nada conectado, el botón lleva a conectar una fuente", async () => {
    await open();
    expect(host.textContent).toContain("Nada conectado aquí todavía");
    act(() => button("Conectar una fuente")!.click());
    await settle();
    expect(window.location.pathname).toBe("/hub/configurar");
    expect(host.textContent).toContain("Planner");
  });

  it("si falla, lo dice y reintentar lo trae", async () => {
    replies["GET /api/hub/connections"] = () => json({ detail: "la base no contesta" }, 503);
    await open();
    expect(host.textContent).toContain("Hub no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/hub/connections"] = () => [];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Nada conectado aquí todavía");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });
});

describe("una conexión", () => {
  it("si no existe lo dice; otro fallo se reintenta", async () => {
    await open(`/hub/${CONNECTION}`);
    expect(host.textContent).toContain("Ya no está");
    expect(button("Reintentar")).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/hub/connections/${CONNECTION}`] = () => json({ detail: "la base no contesta" }, 503);
    await open(`/hub/${CONNECTION}`);
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("axe-core sin errores graves", () => {
  it.each(["/hub/", "/hub/configurar", "/hub/ajustes"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
