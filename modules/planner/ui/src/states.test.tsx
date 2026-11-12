// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { ToastHost } from "@openarga/ui";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Layer, Occurrence } from "./api";
import { App } from "./App";

const PERSONAL: Layer = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Personal",
  tone: 5,
  origin: "own",
  visible: true,
  position: 0,
  display: "events",
  connection_id: null,
  days_off_from: [],
};

const DINNER: Occurrence = {
  id: "e1",
  event_id: "00000000-0000-4000-8000-000000000001",
  calendar_id: PERSONAL.id,
  title: "Cena sintética",
  all_day: false,
  start: new Date(Date.now() + 2 * 3600_000).toISOString(),
  end: new Date(Date.now() + 3 * 3600_000).toISOString(),
  tz: "Europe/Madrid",
  location: "Casa",
  notes: null,
  url: null,
  status: "confirmed",
  original_start: null,
  rrule: null,
  repeat: null,
  moved: false,
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
  Element.prototype.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
    }) as never;
  class Watcher {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = Watcher;
  (globalThis as { IntersectionObserver?: unknown }).IntersectionObserver = Watcher;
});

beforeEach(() => {
  void reset();
  replies = {
    "GET /api/planner/calendars": () => [PERSONAL],
    "GET /api/planner/occurrences": () => [DINNER],
    "GET /api/planner/version": () => ({ version: "1.0.0" }),
    "GET /api/planner/subscriptions/catalogue": () => ({ groups: [], sources: [], others: [] }),
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
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/planner/semana") {
  window.history.replaceState(null, "", path);
  act(() =>
    root.render(
      <ToastHost>
        <App />
      </ToastHost>,
    ),
  );
  await settle();
}

async function serious(): Promise<string[]> {
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("la semana", () => {
  it("mientras llega, el esqueleto", async () => {
    replies["GET /api/planner/occurrences"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("con lo suyo, sus eventos", async () => {
    await open();
    expect(host.textContent).toContain("Cena sintética");
  });

  it("si falla, lo dice y reintentar lo trae", async () => {
    replies["GET /api/planner/occurrences"] = () => json({ detail: "la base no contesta" }, 503);
    await open();
    expect(host.textContent).toContain("Planner no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/planner/occurrences"] = () => [DINNER];
    await act(async () => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Cena sintética");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });
});

describe("la agenda", () => {
  it("sin nada, el botón crea el primero", async () => {
    replies["GET /api/planner/occurrences"] = () => [];
    await open("/planner/agenda");
    expect(host.textContent).toContain("Nada en los próximos 60 días");
    act(() => button("Nuevo evento")!.click());
    await settle();
    expect(document.body.textContent).toContain("Crear");
  });
});

describe("un evento", () => {
  it("se abre al lado, por la dirección", async () => {
    await open(`/planner/semana?event=${DINNER.event_id}`);
    const detail = host.querySelector('[role="region"][aria-label="Evento"]');
    expect(detail?.textContent).toContain("Cena sintética");
    expect(detail?.textContent).toContain("Casa");
  });
});

describe("las suscripciones", () => {
  it("si Hub no contesta, se reintenta; sin fuentes, lleva a Hub", async () => {
    replies["GET /api/planner/subscriptions/catalogue"] = () => json({ detail: "sin hub" }, 503);
    await open();
    await act(async () => button("Suscripciones")?.click() ?? document.querySelector<HTMLButtonElement>('[aria-label="Suscripciones: añadir o quitar"]')!.click());
    await settle();
    expect(document.body.textContent).toContain("Hub no contesta");

    replies["GET /api/planner/subscriptions/catalogue"] = () => ({ groups: [], sources: [], others: [] });
    await act(async () => button("Reintentar")!.click());
    await settle();
    expect(document.body.textContent).toContain("Nada que suscribir todavía");
    expect(button("Ir a Hub")).toBeDefined();
  });
});

describe("axe-core sin errores graves", () => {
  it.each(["/planner/semana", "/planner/mes", "/planner/agenda", "/planner/dia", `/planner/semana?event=${DINNER.event_id}`])(
    "%s",
    async (path) => {
      await open(path);
      expect(await serious()).toEqual([]);
    },
  );
});
