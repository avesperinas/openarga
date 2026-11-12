// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Fact, Onboarding, Pill, Recommendation, Settings, Tastes, Today } from "./api";
import { App } from "./App";
import { forYou, shelf } from "./Library";
import { pillState } from "./Today";
import { grouped } from "./You";

const PILL_ID = "0a0a0a0a-0000-4000-8000-00000000a0a0";
const SETTINGS: Settings = {
  pill_on: true,
  pill_time: "09:00",
  pill_minutes: 15,
  pill_language: null,
  pill_level: null,
  questions: "sometimes",
  started_at: null,
};
const START: Onboarding = {
  done: false,
  answered: 0,
  total: 2,
  questions: [
    {
      id: null,
      origin: "start",
      bank_key: "start.families",
      kind: "many",
      text: "¿De qué te gusta aprender?",
      why: "Para saber qué temas traerte.",
      options: [
        { value: "historia", label: "Historia" },
        { value: "ciencia", label: "Ciencia y universo" },
      ],
    },
    {
      id: null,
      origin: "start",
      bank_key: "start.time",
      kind: "one",
      text: "¿A qué hora te viene bien?",
      why: "Te aviso a esa hora.",
      options: [{ value: "09:00", label: "9:00" }],
    },
  ],
};
const PILL: Pill = {
  id: PILL_ID,
  day: "2026-11-10",
  origin: "daily",
  run_key: "pill:2026-11-10",
  parent_id: null,
  depth: 0,
  family_key: "historia",
  topic: "La batalla de Leuctra",
  hook: null,
  language: "es",
  minutes: 15,
  headline: "La columna que rompió Esparta",
  lead: "Un ejército que nunca perdía y una idea sencilla.",
  sections: [
    { title: "El orden oblicuo", text: "Primero.\n\nSegundo." },
    { title: "Lo que vino después", text: "Tercero." },
  ],
  to_tell: "Esparta no perdía una batalla campal desde hacía generaciones.",
  to_think: "¿Por qué tardó tanto?",
  branches: [
    { title: "Epaminondas", why: "El general" },
    { title: "El Batallón Sagrado", why: "150 parejas" },
    { title: "La caída de Esparta", why: "De Leuctra a la nada" },
  ],
  sources: [{ title: "Batalla de Leuctra", url: "https://es.wikipedia.org/wiki/Batalla_de_Leuctra" }],
  glossary: [],
  reaction: null,
  read_at: "2026-11-10T09:00:00Z",
  created_at: "2026-11-10T08:40:00Z",
};
const FACT: Fact = {
  id: "f1",
  day: "2026-11-10",
  family_key: "ciencia",
  text: "Un dato cierto y sorprendente sobre el universo.",
  detail: null,
  source: { title: "Fuente", url: "https://example.org" },
  reaction: null,
  created_at: "2026-11-10T08:40:00Z",
};
const pick = (extra: Partial<Recommendation> = {}): Recommendation => ({
  id: "p1",
  kind: "book",
  list: "read",
  title: "Una novela histórica",
  creators: ["Una autora"],
  year: 2008,
  length: "720 páginas",
  language: "es",
  why: "Porque te gustó la anterior",
  because: [],
  origin: "weekly",
  pill_id: null,
  verified: "catalog",
  links: [{ label: "Open Library", url: "https://openlibrary.org/isbn/9788466648769" }],
  state: "new",
  collections: [],
  rating: null,
  more_like: null,
  note: null,
  sent_to: null,
  has_cover: false,
  created_at: "2026-11-09T17:00:00Z",
  updated_at: "2026-11-09T17:00:00Z",
  ...extra,
});
const TASTES: Tastes = {
  traits: [
    {
      id: "t1",
      facet: "genre",
      label: "Novela histórica",
      stance: 2,
      source: "seen",
      evidence: "6 novelas, media 4,2",
      status: "proposed",
      updated_at: "2026-11-09T17:00:00Z",
    },
    { id: "t2", facet: "avoid", label: "Fútbol", stance: -2, source: "said", evidence: null, status: "confirmed", updated_at: "2026-11-09T17:00:00Z" },
  ],
  families: [
    { key: "historia", name: "Historia", hue: 3, glyph: "landmark", themes: "", weight: 2, outside: false },
    { key: "ciencia", name: "Ciencia y universo", hue: 5, glyph: "atom", themes: "", weight: 1, outside: false },
  ],
  sources: [],
  settings: SETTINGS,
  onboarding: START,
};
const day = (extra: Partial<Today> = {}): Today => ({
  day: "2026-11-10",
  pill: PILL,
  asked: null,
  facts: [FACT],
  picks: [pick({ origin: "pill", pill_id: PILL_ID })],
  question: null,
  onboarding: { ...START, done: true, answered: 2, questions: [] },
  settings: SETTINGS,
  streak: 3,
  unread: 0,
  latest: null,
  waiting: [],
  ...extra,
});

let root: Root;
let host: HTMLElement;
let replies: Record<string, () => unknown>;
let asked: string[];

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }) as never;
});

beforeEach(() => {
  void reset();
  asked = [];
  replies = {
    "GET /api/insights/profile": () => ({ name: "Txuri", about: "", named: true }),
    "GET /api/insights/today": () => day(),
    "GET /api/insights/tastes": () => TASTES,
    "GET /api/insights/picks": () => [pick(), pick({ id: "p2", title: "Guardado", state: "saved" })],
    "GET /api/insights/pills": () => [],
    "GET /api/insights/onboarding": () => START,
    "GET /api/insights/version": () => ({ version: "1.1.0" }),
    [`POST /api/insights/pills/${PILL_ID}/read`]: () => PILL,
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
    for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path: string) {
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

describe("lo que se decide sin pintar", () => {
  it("qué decir de la píldora que aún no está", () => {
    expect(pillState(day())).toBe("ready");
    expect(pillState(day({ pill: null }))).toBe("later");
    expect(pillState(day({ pill: null, settings: { ...SETTINGS, pill_on: false } }))).toBe("off");
    const waiting = { id: "a", kind: "pill", key: "pill:x", origin: "daily", parent_id: null, branch: null, family_key: null, asked_at: "", detail: null, pill_id: null } as const;
    expect(pillState(day({ pill: null, asked: { ...waiting, state: "waiting" } }))).toBe("writing");
    expect(pillState(day({ pill: null, asked: { ...waiting, state: "failed" } }))).toBe("failed");
  });

  it("la biblioteca: lo sin abrir arriba y lo de cada lista, lo hecho al final", () => {
    const all = [
      pick({ id: "a", state: "done", updated_at: "2026-11-10" }),
      pick({ id: "b", state: "doing" }),
      pick({ id: "c", state: "new" }),
      pick({ id: "d", state: "saved", list: "watch", kind: "film" }),
    ];
    expect(shelf(all, "read", false).map((one) => one.id)).toEqual(["b", "a"]);
    expect(shelf(all, "read", true).map((one) => one.id)).toEqual(["b"]);
    expect(forYou(all).map((one) => one.id)).toEqual(["c"]);
  });

  it("lo confirmado por faceta, sin lo propuesto ni lo descartado", () => {
    expect(grouped(TASTES.traits).map((group) => [group.facet, group.traits.length])).toEqual([["avoid", 1]]);
  });
});

describe("hoy", () => {
  it("la píldora entera, con su barra, sus datos, sus ramas y lo de seguir", async () => {
    await open("/insights/");

    expect(host.textContent).toContain("Tu píldora");
    expect(host.textContent).toContain("La columna que rompió Esparta");
    expect(host.textContent).toContain("Para contar");
    expect(host.textContent).toContain("Datos de hoy");
    expect(host.textContent).toContain("Quiero saber más sobre…");
    expect(host.textContent).toContain("Para seguir");
    expect(host.querySelector('[aria-label="Partes de la píldora"]')).not.toBeNull();
    expect(host.textContent).toContain("Hablar con Txuri");
    expect(await serious()).toEqual([]);
  });

  it("antes de su hora dice cuándo llega y se puede pedir ya", async () => {
    replies["GET /api/insights/today"] = () => day({ pill: null, facts: [], picks: [] });
    replies["POST /api/insights/pills/more"] = () => ({
      id: "a1",
      kind: "more",
      key: "more:x",
      origin: "surprise",
      parent_id: null,
      branch: null,
      family_key: "ciencia",
      asked_at: "2026-11-10T08:00:00Z",
      state: "waiting",
      detail: null,
      pill_id: null,
    });
    await open("/insights/");
    expect(host.textContent).toContain("Tu píldora llega a las 09:00");

    act(() => button("Pídela ahora")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/pills/more");
    expect(host.textContent).toContain("está escribiendo otra píldora");
  });

  it("la pregunta de Insights se contesta con un toque", async () => {
    replies["GET /api/insights/today"] = () =>
      day({
        question: {
          id: "q1",
          origin: "pass",
          bank_key: null,
          kind: "either",
          text: "¿Sagas o novelas que se cierran?",
          why: "Has terminado varias sagas",
          options: [
            { value: "saga", label: "Sagas" },
            { value: "one", label: "Que se cierren" },
          ],
        },
      });
    replies["POST /api/insights/questions/q1/answer"] = () => ({});
    await open("/insights/");
    expect(host.textContent).toContain("Txuri te pregunta");

    act(() => button("Sagas")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/questions/q1/answer");
  });

  it("la primera vez invita a «Que te conozca»", async () => {
    replies["GET /api/insights/today"] = () => day({ onboarding: START, pill: null });
    await open("/insights/");
    act(() => button("Empezar")!.click());
    await settle();
    expect(window.location.pathname).toBe("/insights/conocerte");
  });

  it("si falla, reintentar", async () => {
    replies["GET /api/insights/today"] = () => json({ detail: "no" }, 500);
    await open("/insights/");
    expect(host.textContent).toContain("No se pudo abrir tu día");

    replies["GET /api/insights/today"] = () => day();
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("La columna que rompió Esparta");
  });
});

describe("la biblioteca", () => {
  it("lo de esta semana en tarjetas, y guardar lo pasa a la lista", async () => {
    replies["POST /api/insights/picks/p1/save"] = () => pick({ state: "saved", sent_to: "library" });
    await open("/insights/biblioteca");
    expect(host.textContent).toContain("Para ti esta semana");
    expect(host.textContent).toContain("Porque te gustó la anterior");
    expect(host.textContent).toContain("Guardado");

    act(() => button("Guardar")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/picks/p1/save");
    expect(await serious()).toEqual([]);
  });

  it("sin nada, dice cómo llega", async () => {
    replies["GET /api/insights/picks"] = () => [];
    await open("/insights/biblioteca");
    expect(host.textContent).toContain("Nada guardado aquí todavía");
  });
});

describe("tú", () => {
  it("lo propuesto se confirma, y lo que sabe sale con de dónde", async () => {
    replies["PUT /api/insights/traits/t1"] = () => ({ ...TASTES.traits[0], status: "confirmed" });
    await open("/insights/tu");
    expect(host.textContent).toContain("¿Es así?");
    expect(host.textContent).toContain("6 novelas, media 4,2");
    expect(host.textContent).toContain("Fútbol");
    expect(host.textContent).toContain("Tus temas");

    act(() => (host.querySelector('[aria-label="Sí: Novela histórica"]') as HTMLButtonElement).click());
    await settle();
    expect(asked).toContain("PUT /api/insights/traits/t1");
    expect(await serious()).toEqual([]);
  });

  it("«Que te conozca», una pregunta cada vez", async () => {
    replies["POST /api/insights/onboarding/start.families"] = () => ({ ...START, answered: 1, questions: START.questions.slice(1) });
    await open("/insights/conocerte");
    expect(host.textContent).toContain("¿De qué te gusta aprender?");
    expect(host.textContent).toContain("1 de 2");

    act(() => button("Historia")!.click());
    act(() => button("Seguir")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/onboarding/start.families");
    expect(host.textContent).toContain("¿A qué hora te viene bien?");
    expect(await serious()).toEqual([]);
  });
});
