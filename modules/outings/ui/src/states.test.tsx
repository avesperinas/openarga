// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const EVENT = "0a0a0a0a-0000-4000-8000-00000000e0e0";
const WISH = "0a0a0a0a-0000-4000-8000-00000000a0a0";

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
    "GET /api/outings/mine": () => ({ from: "2026-11-01", to: "2026-11-30", events: [] }),
    "GET /api/outings/foryou": () => [],
    "GET /api/outings/explore": () => ({ first: "2026-11-01", last: "2027-01-31", total: 0, events: [] }),
    "GET /api/outings/wishes": () => [],
    "GET /api/outings/planned": () => [],
    "GET /api/outings/interests": () => [],
    "GET /api/outings/agenda/sources": () => ({ plugged: [], offered: [], failed: null }),
    "GET /api/outings/version": () => ({ version: "1.0.0" }),
    "GET /api/kernel/spaces": () => [],
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

async function open(path = "/outings/") {
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

describe("la agenda", () => {
  it("mientras llega, el esqueleto", async () => {
    replies["GET /api/outings/mine"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("vacía, el botón lleva a Explorar", async () => {
    await open();
    expect(host.textContent).toContain("Tu agenda está vacía");
    act(() => button("Explorar")!.click());
    await settle();
    expect(window.location.pathname).toBe("/outings/explorar");
  });

  it("si falla, lo dice y reintentar lo trae", async () => {
    replies["GET /api/outings/mine"] = () => json({ detail: "la base no contesta" }, 503);
    await open();
    expect(host.textContent).toContain("Outings no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/outings/mine"] = () => ({ from: "2026-11-01", to: "2026-11-30", events: [] });
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Tu agenda está vacía");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });
});

describe("explorar", () => {
  it("sin nada en la agenda, el botón pide a tu Claude que la llene", async () => {
    await open("/outings/explorar");
    expect(host.textContent).toContain("La agenda está vacía");
    expect(button("Actualizar")).toBeDefined();
  });

  it("si falla, se reintenta", async () => {
    replies["GET /api/outings/explore"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/outings/explorar");
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("las ganas", () => {
  it("sin ninguna, el botón apunta la primera", async () => {
    await open("/outings/ganas");
    expect(host.textContent).toContain("Nada apuntado todavía");
    expect(button("Apuntar")).toBeDefined();
  });

  it("una que ya no está lo dice; otro fallo se reintenta", async () => {
    await open(`/outings/ganas/${WISH}`);
    expect(host.textContent).toContain("Ya no está");
    expect(button("Reintentar")).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/outings/wishes/${WISH}`] = () => json({ detail: "la base no contesta" }, 503);
    await open(`/outings/ganas/${WISH}`);
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("un evento", () => {
  it("si no existe lo dice", async () => {
    await open(`/outings/eventos/${EVENT}`);
    expect(host.textContent).toContain("Ya no está");
  });
});

describe("los ajustes", () => {
  it("si no se pueden leer, se reintenta", async () => {
    replies["GET /api/outings/interests"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/outings/ajustes");
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("axe-core sin errores graves", () => {
  it.each(["/outings/", "/outings/explorar", "/outings/ganas", "/outings/ajustes"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
