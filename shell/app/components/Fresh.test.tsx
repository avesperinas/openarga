// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CatalogueEntry, DesktopLayout, Envelope } from "../lib/kernel";
import { Dashboard } from "./Dashboard";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let visibility: "visible" | "hidden" = "visible";
Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
let narrow = false;
const widthListeners = new Set<() => void>();
window.matchMedia = ((query: string) => ({
  get matches() {
    return query.includes("max-width: 559px") ? narrow : false;
  },
  media: query,
  addEventListener: (_: string, listener: () => void) => widthListeners.add(listener),
  removeEventListener: (_: string, listener: () => void) => widthListeners.delete(listener),
})) as unknown as typeof window.matchMedia;
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
Element.prototype.scrollTo = function () {};
Element.prototype.scrollIntoView = function () {};

const entry = (id: string, kind: CatalogueEntry["kind"], refresh: number): CatalogueEntry => ({
  source: "goals",
  id,
  title: id,
  hue: 1,
  kind,
  shape: kind === "tasks" ? "list" : "number",
  sizes: ["4x4"],
  endpoint: `/api/goals/widgets/${id}`,
  refresh,
  link: null,
});

const TASKS = entry("tasks", "tasks", 300);
const KPI = entry("kpi", "kpi", 300);

const desk = (ids: string[]): DesktopLayout => ({
  updated_at: null,
  default: false,
  placements: {},
  pages: [
    {
      id: "p",
      items: ids.map((id) => ({ instance_id: `i-${id}`, source: "goals", widget: id, size: "4x4" })),
    },
  ],
});

const tasks = (list: { id: string; title: string }[]): Envelope => ({
  state: "ready",
  updated_at: "2026-10-21T08:00:00Z",
  body: { tasks: list, checkable: true, count: list.length },
});
const kpi = (value: string): Envelope => ({
  state: "ready",
  updated_at: "2026-10-21T08:00:00Z",
  body: { value },
});

type Call = { url: string; resolve: (response: Response) => void };
let calls: Call[] = [];
let root: Root;
let container: HTMLDivElement;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
  vi.setSystemTime(new Date("2026-10-21T08:00:00Z"));
  visibility = "visible";
  narrow = false;
  calls = [];
  globalThis.fetch = vi.fn(
    (input: RequestInfo | URL) =>
      new Promise<Response>((resolve) => calls.push({ url: String(input), resolve })),
  ) as typeof fetch;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

const flush = async () => {
  for (let i = 0; i < 5; i++) await act(async () => await Promise.resolve());
};

const mount = async (
  catalogue: CatalogueEntry[],
  ids: string[],
  data: Record<string, Envelope | null>,
) => {
  await act(async () =>
    root.render(
      <Dashboard
        desks={{ mobile: desk(ids), desktop: desk(ids) }}
        device="desktop"
        catalogue={catalogue}
        data={data}
      />,
    ),
  );
  await flush();
};

const comeBack = async () => {
  await act(async () => document.dispatchEvent(new Event("visibilitychange")));
  await flush();
};

const batches = () => calls.filter((call) => call.url.startsWith("/envelopes"));
const keysOf = (call: Call) => new URL(call.url, "http://x").searchParams.getAll("w");

describe("el escritorio se pone al día solo (T-V07)", () => {
  it("con la pestaña oculta no pide nada; al volver, una sola petición en lote", async () => {
    await mount([KPI, TASKS], ["kpi", "tasks"], { "goals/kpi": kpi("1"), "goals/tasks": tasks([]) });
    visibility = "hidden";
    await act(async () => {
      vi.advanceTimersByTime(3_600_000);
    });
    await flush();
    expect(calls).toEqual([]);

    visibility = "visible";
    await comeBack();
    expect(calls.map((call) => keysOf(call))).toEqual([["goals/kpi", "goals/tasks"]]);
  });

  it("un sobre que no llega en el lote no borra el que se ve", async () => {
    await mount([KPI], ["kpi"], { "goals/kpi": kpi("bueno") });
    vi.setSystemTime(new Date("2026-10-21T08:06:00Z"));
    await comeBack();
    await act(async () => batches()[0]!.resolve(json({ "goals/kpi": null })));
    await flush();

    expect(container.textContent).toContain("bueno");
  });

  it("un lote que salió antes de tachar una tarea no la devuelve al llegar", async () => {
    const before = tasks([
      { id: "t1", title: "Comprar pan" },
      { id: "t2", title: "Llamar" },
    ]);
    await mount([TASKS], ["tasks"], { "goals/tasks": before });
    vi.setSystemTime(new Date("2026-10-21T08:06:00Z"));
    await comeBack();
    const batch = batches()[0]!;

    const check = container.querySelector('[aria-label="Marcar hecha Comprar pan"]') as HTMLButtonElement;
    await act(async () => check.click());
    await flush();
    const post = calls.find((call) => call.url.includes("/act"))!;
    await act(async () => post.resolve(json(tasks([{ id: "t2", title: "Llamar" }]))));
    await flush();
    await act(async () => batch.resolve(json({ "goals/tasks": before })));
    await flush();

    expect(container.textContent).not.toContain("Comprar pan");
    expect(container.textContent).toContain("Llamar");
  });

  it("estrechar la ventana y volver no devuelve el sobre de la carga", async () => {
    await mount([KPI], ["kpi"], { "goals/kpi": kpi("1.000 € de la carga") });
    vi.setSystemTime(new Date("2026-10-21T08:06:00Z"));
    await comeBack();
    await act(async () => batches()[0]!.resolve(json({ "goals/kpi": kpi("2.500 € de ahora") })));
    await flush();
    expect(container.textContent).toContain("2.500");

    calls = [];
    narrow = true;
    await act(async () => widthListeners.forEach((listener) => listener()));
    await flush();
    narrow = false;
    await act(async () => widthListeners.forEach((listener) => listener()));
    await flush();

    expect(container.textContent).toContain("2.500");
    expect(container.textContent).not.toContain("1.000");
    await comeBack();
    expect(batches()).toEqual([]);
  });

  it("lo que vence a la vez va de 64 en 64, y lo que no cabe, en la vuelta siguiente", async () => {
    const many = Array.from({ length: 70 }, (_, index) => entry(`w${index}`, "kpi", 300));
    await mount(
      many,
      many.map((one) => one.id),
      Object.fromEntries(many.map((one) => [`goals/${one.id}`, kpi("0")])),
    );
    vi.setSystemTime(new Date("2026-10-21T08:06:00Z"));
    await comeBack();
    const first = batches()[0]!;
    expect(keysOf(first)).toHaveLength(64);

    await act(async () => first.resolve(json({})));
    await flush();
    await comeBack();
    const second = batches()[1]!;
    expect(keysOf(second)).toHaveLength(6);
    expect(new Set([...keysOf(first), ...keysOf(second)]).size).toBe(70);
  });
});
