// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Book, YearStats } from "./api";
import { App } from "./App";

const ID = "00000000-0000-4000-8000-000000000001";

const BOOK: Book = {
  id: ID,
  edition: "catalog",
  edition_id: "e",
  title: "Libro sintético",
  subtitle: null,
  authors: ["Autora Sintética"],
  pages: 300,
  language: "es",
  year: 2020,
  isbn13: null,
  has_cover: false,
  source: "app",
  days: 20,
  status: "read",
  started_on: "2026-09-01",
  finished_on: "2026-09-20",
  rating: 4,
  format: "paper",
  genre: "novel",
  note: null,
};

const EMPTY_YEAR: YearStats = {
  year: 2026,
  years: [2026],
  books: 0,
  pages: 0,
  goal: null,
  goal_pace: null,
  average_rating: null,
  pages_per_day: 0,
  months: [],
  days: {},
  genres: [],
  formats: [],
  languages: [],
  authors: [],
  ratings: {},
  longest: null,
  fastest: null,
};

const YEAR: YearStats = {
  ...EMPTY_YEAR,
  books: 1,
  pages: 300,
  goal: 12,
  average_rating: 4,
  pages_per_day: 15,
  months: Array.from({ length: 12 }, (_, index) => ({
    month: index + 1,
    label: ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"][index]!,
    books: index === 8 ? 1 : 0,
    pages: index === 8 ? 300 : 0,
  })),
  days: { "2026-09-10": 15 },
  genres: [{ id: "novel", name: "Novela", books: 1, pages: 300 }],
  authors: [{ id: "a", name: "Autora Sintética", books: 1, pages: 300 }],
  ratings: { "4": 1 },
  longest: { id: ID, title: "Libro sintético", pages: 300, days: 20 },
  fastest: { id: ID, title: "Libro sintético", pages: 300, days: 20 },
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
    ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }) as never;
});

beforeEach(() => {
  reset();
  window.history.replaceState(null, "", "/library/");
  replies = {
    "GET /api/library/books": () => [BOOK],
    "GET /api/library/genres": () => [{ id: "novel", name: "Novela" }],
    "GET /api/library/version": () => ({ version: "1.0.0" }),
    "GET /api/library/stats": () => YEAR,
    [`GET /api/library/books/${ID}`]: () => BOOK,
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
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
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

describe("la estantería", () => {
  it("mientras llega, el esqueleto", async () => {
    replies["GET /api/library/books"] = () => new Promise(() => undefined);
    await open("/library/");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("vacía, dice qué hacer y el botón abre el alta", async () => {
    replies["GET /api/library/books"] = () => [];
    await open("/library/");
    expect(host.textContent).toContain("Todavía no hay libros");

    act(() => button("Añadir un libro")!.click());
    await settle();
    expect(document.querySelector("dialog, [role=dialog]")).not.toBeNull();
  });

  it("si falla, lo dice y reintentar la trae", async () => {
    replies["GET /api/library/books"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/library/");
    expect(host.textContent).toContain("No se ha podido leer la estantería");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/library/books"] = () => [BOOK];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).not.toContain("No se ha podido leer la estantería");
    expect(host.querySelector('[aria-label="Libro sintético"]')).not.toBeNull();
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open("/library/");
    expect(host.textContent).toContain("Sin conexión");
  });

  it("axe-core sin errores graves", async () => {
    await open("/library/");
    expect(await serious()).toEqual([]);
  });
});

describe("las estadísticas", () => {
  it("un año sin libros lleva a la estantería", async () => {
    replies["GET /api/library/stats"] = () => EMPTY_YEAR;
    await open("/library/estadisticas");
    expect(host.textContent).toContain("Nada leído en 2026");

    act(() => button("Ir a la estantería")!.click());
    await settle();
    expect(window.location.pathname).toBe("/library/");
  });

  it("si fallan, reintentar", async () => {
    replies["GET /api/library/stats"] = () => json({ detail: "no" }, 500);
    await open("/library/estadisticas");
    expect(host.textContent).toContain("No se han podido leer las cifras");

    replies["GET /api/library/stats"] = () => YEAR;
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Páginas por mes");
  });

  it("axe-core sin errores graves", async () => {
    await open("/library/estadisticas");
    expect(host.textContent).toContain("Páginas por mes");
    expect(await serious()).toEqual([]);
  });
});

describe("la ficha", () => {
  it("si no se puede abrir, reintentar", async () => {
    replies["GET /api/library/books"] = () => [];
    replies[`GET /api/library/books/${ID}`] = () => json({ detail: "no" }, 500);
    await open(`/library/libro/${ID}`);
    expect(host.textContent).toContain("No se ha podido abrir el libro");

    replies[`GET /api/library/books/${ID}`] = () => BOOK;
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.querySelector(".app-shell-detail h1")?.textContent).toContain("Libro sintético");
  });

  it("axe-core sin errores graves", async () => {
    await open(`/library/libro/${ID}`);
    expect(await serious()).toEqual([]);
  });
});
