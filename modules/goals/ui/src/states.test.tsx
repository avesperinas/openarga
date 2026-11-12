// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const GOAL = "0a0a0a0a-0000-4000-8000-00000000a0a0";

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
    "GET /api/goals/categories": () => [],
    "GET /api/goals/goals": () => [],
    "GET /api/goals/goals?state=closed": () => [],
    "GET /api/goals/tasks": () => [],
    "GET /api/goals/tasks?state=done": () => [],
    "GET /api/goals/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
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

async function open(path = "/goals/metas") {
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

describe("los KPIs", () => {
  it("mientras llegan, el esqueleto", async () => {
    replies["GET /api/goals/goals"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("sin metas, el botón pone la primera", async () => {
    await open();
    expect(host.textContent).toContain("Aún no te has propuesto nada");
    expect(button("Ponerte una meta")).toBeDefined();
  });

  it("si fallan, lo dice y reintentar las trae", async () => {
    replies["GET /api/goals/goals"] = () => json({ detail: "la base no contesta" }, 503);
    await open();
    expect(host.textContent).toContain("KPIs no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/goals/goals"] = () => [];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Aún no te has propuesto nada");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });

  it("una meta que no existe lo dice y vuelve; otro fallo se reintenta", async () => {
    await open(`/goals/meta/${GOAL}`);
    expect(host.textContent).toContain("No se encuentra esta meta");

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/goals/goals/${GOAL}`] = () => json({ detail: "la base no contesta" }, 503);
    await open(`/goals/meta/${GOAL}`);
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("las tareas", () => {
  it("son la portada y la primera pestaña; las metas, la segunda", async () => {
    await open("/goals/");
    expect(host.textContent).toContain("Nada pendiente");
    const tabs = Array.from(host.querySelectorAll("nav button, [role=tab]")).map((one) => one.textContent?.trim());
    expect(tabs.indexOf("Tareas")).toBeLessThan(tabs.indexOf("KPIs"));
    expect(tabs.indexOf("Tareas")).toBeGreaterThanOrEqual(0);
  });

  it("sin tareas, el botón apunta una", async () => {
    await open("/goals/tareas");
    expect(host.textContent).toContain("Nada pendiente");
    expect(button("Apuntar una tarea")).toBeDefined();
  });

  it("si fallan, reintentar", async () => {
    replies["GET /api/goals/tasks"] = () => json({ detail: "no" }, 500);
    await open("/goals/tareas");
    expect(host.querySelector("[role=alert]")).not.toBeNull();

    replies["GET /api/goals/tasks"] = () => [];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Nada pendiente");
  });
});

describe("axe-core sin errores graves", () => {
  it.each(["/goals/", "/goals/metas", "/goals/hechas", "/goals/ajustes"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
