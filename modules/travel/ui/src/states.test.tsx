// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { queue } from "./api";
import { App } from "./App";

const TRIP = "0a0a0a0a-0000-4000-8000-00000000e1c0";

const EMPTY_ATLAS = { trips: [], others: [], home: null, ideas: [] };
const EMPTY_STATS = {
  trips: 0,
  nights: 0,
  km: 0,
  countries: 0,
  regions: 0,
  europe_visited: [],
  europe_total: 44,
  by_year: [],
  km_by_mode: { plane: 0, train: 0, car: 0, bus: 0, boat: 0 },
  top_countries: [],
  cost_per_day: [],
  average_cost_per_day: null,
  spend_per_night_by_country: [],
  nights_calendar: {},
};
const NO_TRIP_TODAY = { day: "2026-11-03", trip: null, sleeping: null, entries: [], here: null, next_trip: null };

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

beforeEach(async () => {
  void reset();
  await queue.bindPerson(`prueba-${Math.random()}`);
  replies = {
    "GET /api/travel/atlas": () => EMPTY_ATLAS,
    "GET /api/travel/stats": () => EMPTY_STATS,
    "GET /api/travel/today": () => NO_TRIP_TODAY,
    "GET /api/travel/me": () => ({ user_id: "00000000-0000-4000-8000-00000000a7e5" }),
    "GET /api/travel/version": () => ({ version: "1.0.0" }),
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
    for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find(
    (one) => one.textContent?.includes(name) || one.getAttribute("aria-label") === name,
  );

async function open(path: string) {
  window.history.replaceState(null, "", path);
  act(() => root.render(<App />));
  await settle();
}

async function shows(text: string) {
  await vi.waitFor(async () => {
    await settle();
    expect(host.textContent).toContain(text);
  });
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("los viajes", () => {
  it("mientras llegan, el esqueleto", async () => {
    replies["GET /api/travel/atlas"] = () => new Promise(() => undefined);
    await open("/travel/viajes");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("sin viajes, el botón añade el primero", async () => {
    await open("/travel/viajes");
    expect(host.textContent).toContain("Aún no hay viajes hechos");
    expect(button("Añadir un viaje")).toBeDefined();
  });

  it("si falla, lo dice y reintentar lo trae", async () => {
    replies["GET /api/travel/atlas"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/travel/viajes");
    expect(host.textContent).toContain("Travel no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/travel/atlas"] = () => EMPTY_ATLAS;
    await act(async () => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Aún no hay viajes hechos");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open("/travel/viajes");
    expect(host.textContent).toContain("Sin conexión");
  });
});

describe("los planes", () => {
  it("sin ninguno, el botón planea uno", async () => {
    await open("/travel/planes");
    expect(host.textContent).toContain("Sin planes");
    expect(button("Planear un viaje")).toBeDefined();
  });
});

describe("hoy", () => {
  it("sin viaje en curso, el botón planea uno", async () => {
    await open("/travel/hoy");
    expect(host.textContent).toContain("Hoy no hay viaje en curso");
    expect(button("Planear un viaje")).toBeDefined();
  });

  it("si falla, se reintenta", async () => {
    replies["GET /api/travel/today"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/travel/hoy");
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("el diario de hoy", () => {
  const ONGOING = {
    ...NO_TRIP_TODAY,
    trip: { id: TRIP, title: "Lisboa", number: 2, days: 4, day_title: null },
    journal: null,
  };

  it("se escribe sin red: se queda y espera para enviarse", async () => {
    await queue.bindPerson("00000000-0000-4000-8000-00000000a7e5");
    replies["GET /api/travel/today"] = () => ONGOING;
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    replies[`PUT /api/travel/trips/${TRIP}/journal`] = () => {
      throw new TypeError("sin red");
    };
    const fetcher = globalThis.fetch as ReturnType<typeof vi.fn>;
    const answer = fetcher.getMockImplementation()!;
    fetcher.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") throw new TypeError("sin red");
      return answer(url, init);
    });
    await open("/travel/hoy");
    await shows("Diario de hoy");

    await act(async () => button("Escribir")!.click());
    const box = host.ownerDocument.querySelector<HTMLTextAreaElement>("textarea")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(box, "Tranvía 28.");
      box.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const save = Array.from(host.ownerDocument.querySelectorAll<HTMLButtonElement>("button")).find(
      (one) => one.textContent === "Guardar",
    )!;
    await act(async () => save.click());
    await settle();

    expect(host.textContent).toContain("Tranvía 28.");
    expect(host.textContent).toContain("1 cambio por enviar");
  });
});

describe("las cifras", () => {
  it("sin viajes, el botón añade el primero", async () => {
    await open("/travel/estadisticas");
    await shows("Aún no hay cifras");
    expect(button("Añadir un viaje")).toBeDefined();
  });
});

describe("las reservas de un viaje", () => {
  it("si no existe lo dice; otro fallo se reintenta", async () => {
    await open(`/travel/viajes/${TRIP}/reservas`);
    await shows("Ya no está");
    expect(button("Reintentar")).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    for (const path of ["", "/days", "/bookings"]) {
      replies[`GET /api/travel/trips/${TRIP}${path}`] = () => json({ detail: "la base no contesta" }, 503);
    }
    await open(`/travel/viajes/${TRIP}/reservas`);
    await shows("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("axe-core sin errores graves", () => {
  it.each([
    ["/travel/viajes", "Aún no hay viajes hechos"],
    ["/travel/planes", "Sin planes"],
    ["/travel/hoy", "Hoy no hay viaje en curso"],
    ["/travel/estadisticas", "Aún no hay cifras"],
  ])("%s", async (path, text) => {
    await open(path);
    await shows(text);
    expect(await serious()).toEqual([]);
  });
});
