// @vitest-environment jsdom
import { invalidate, prime, reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Insight, Profile } from "./api";
import { App } from "./App";

const ID = "0a0a0a0a-0000-4000-8000-00000000a0a0";

const figure = { label: "cenas fuera esta semana", value: 4, unit: null, baseline: 2, baseline_label: "tu media" };

const WEEK: Insight = {
  id: ID,
  kind: "weekly",
  domain: "cross",
  topic: "semana:2026-w42",
  title: "Una semana de mucho fuera",
  body: "Cenaste fuera cuatro veces.",
  figures: [figure],
  affects: "el colchón de diciembre",
  action: "Tres cenas en casa de lunes a jueves.",
  created_at: "2026-10-18T17:00:00Z",
  read_at: null,
  rating: null,
  rated_at: null,
  proposals: [
    { what: "Tres cenas en casa de lunes a jueves", figure, how: "Shopping: añadir a la lista lo de tres cenas" },
    { what: "Dos sesiones de fuerza martes y jueves", figure, how: "Planner: bloque de 45 min a las 19:00" },
    { what: "Acostarte antes de las 23:30 entre semana", figure, how: "Planner: aviso a las 23:00" },
  ],
};

const PROFILE: Profile = { name: "Txuri", about: "", named: true };

type Reply = () => unknown;

let root: Root;
let host: HTMLElement;
let replies: Record<string, Reply>;
let asked: string[];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
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
    "GET /api/insights/profile": () => PROFILE,
    "GET /api/insights/insights": () => [WEEK],
    "GET /api/insights/signals": () => [],
    "GET /api/insights/runs": () => [],
    "GET /api/insights/threads": () => [],
    "GET /api/insights/version": () => ({ version: "1.0.0" }),
    [`POST /api/insights/insights/${ID}/read`]: () => ({ ...WEEK, read_at: "2026-10-18T18:00:00Z" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      asked.push(key);
      const reply = replies[key];
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

async function open(path = "/insights/consejos") {
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

describe("la bandeja", () => {
  it("mientras llegan los consejos, el esqueleto", async () => {
    replies["GET /api/insights/insights"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("sin consejos, dice qué hacer y el botón lleva a contarle qué te importa", async () => {
    replies["GET /api/insights/insights"] = () => [];
    await open();
    expect(host.textContent).toContain("Txuri todavía no te ha dicho nada");

    act(() => button("Contarle qué te importa")!.click());
    await settle();
    expect(window.location.pathname).toBe("/insights/tu");
  });

  it("si fallan los consejos, lo dice y reintentar los trae", async () => {
    replies["GET /api/insights/insights"] = () => json({ detail: "la base no contesta" }, 503);
    await open();
    expect(host.textContent).toContain("No se pudieron leer los consejos");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/insights/insights"] = () => [WEEK];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Una semana de mucho fuera");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });

  it("axe-core sin errores graves", async () => {
    await open();
    expect(await serious()).toEqual([]);
  });
});

describe("el resumen del domingo", () => {
  it("trae sus propuestas numeradas, con su cifra y cómo pedírsela a Claude", async () => {
    await open(`/insights/consejo/${ID}`);

    expect(asked).toContain(`POST /api/insights/insights/${ID}/read`);
    expect(host.textContent).toContain("La semana que viene");
    expect(host.textContent).toContain("1. Tres cenas en casa de lunes a jueves");
    expect(host.textContent).toContain("3. Acostarte antes de las 23:30 entre semana");
    expect(host.textContent).toContain("Planner: bloque de 45 min a las 19:00");
    expect(host.textContent).toContain("díselo a Claude");
    expect(await serious()).toEqual([]);
  });

  it("un aviso suelto sigue diciendo qué haría", async () => {
    const alert = { ...WEEK, kind: "alert" as const, proposals: [] };
    replies[`POST /api/insights/insights/${ID}/read`] = () => alert;
    replies["GET /api/insights/insights"] = () => [alert];
    await open(`/insights/consejo/${ID}`);

    expect(host.textContent).toContain("Qué haría");
    expect(host.textContent).not.toContain("La semana que viene");
  });

  it("si no se puede abrir, reintentar", async () => {
    replies["GET /api/insights/insights"] = () => [];
    replies[`POST /api/insights/insights/${ID}/read`] = () => json({ detail: "no" }, 500);
    await open(`/insights/consejo/${ID}`);
    expect(host.textContent).toContain("No se pudo abrir el consejo");

    replies[`POST /api/insights/insights/${ID}/read`] = () => WEEK;
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("La semana que viene");
  });
});

describe("hablar", () => {
  it("sin conversaciones, el botón empieza una", async () => {
    await open("/insights/hablar");
    expect(host.textContent).toContain("Pregúntale lo que quieras a Txuri");

    act(() => button("Empezar a hablar")!.click());
    await settle();
    expect(window.location.pathname).toBe("/insights/hablar/nueva");
  });

  it("si fallan las conversaciones, reintentar", async () => {
    replies["GET /api/insights/threads"] = () => json({ detail: "no" }, 500);
    await open("/insights/hablar");
    expect(host.textContent).toContain("No se pudieron leer las conversaciones");

    replies["GET /api/insights/threads"] = () => [];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Pregúntale lo que quieras");
  });

  it("axe-core sin errores graves, también en los ajustes", async () => {
    await open("/insights/hablar");
    expect(await serious()).toEqual([]);
    act(() => root.unmount());
    root = createRoot(host);
    await open("/insights/ajustes");
    expect(await serious()).toEqual([]);
  });
});

describe("los ajustes", () => {
  it("los campos se llenan con lo del servidor, no con lo guardado en el dispositivo", async () => {
    prime<Profile>("profile", { name: "Otro", about: "lo de otra persona", named: true });
    invalidate("profile");
    const waiting: ((profile: Profile) => void)[] = [];
    replies["GET /api/insights/profile"] = () => new Promise<Profile>((resolve) => waiting.push(resolve));
    await open("/insights/ajustes");
    expect(host.querySelector("textarea")).toBeNull();

    await act(async () => waiting.forEach((answer) => answer({ ...PROFILE, about: "lo mío" })));
    await settle();
    expect((host.querySelector("textarea") as HTMLTextAreaElement).value).toBe("lo mío");
  });
});
