// @vitest-environment jsdom
import { reset } from "@openarga/app";
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
  days: null,
  status: "reading",
  started_on: "2026-09-01",
  finished_on: null,
  rating: null,
  format: "paper",
  genre: "novel",
  note: null,
};

const STATS: YearStats = {
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

type Reply = (init?: RequestInit) => Promise<unknown> | unknown;

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
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }) as never;
});

beforeEach(() => {
  reset();
  window.history.replaceState(null, "", "/library/");
  asked = [];
  replies = {
    "GET /api/library/books": () => [BOOK],
    "GET /api/library/genres": () => [],
    "GET /api/library/version": () => ({ version: "1.0.0" }),
    "GET /api/library/stats": () => STATS,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      asked.push(key);
      const reply = replies[key];
      if (!reply) return json({ detail: "no existe" }, 404);
      const body = await reply(init);
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

const tab = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>(".tab-bar button")).find((one) => one.textContent?.includes(name))!;
const times = (key: string) => asked.filter((one) => one === key).length;

describe("Library con el kit de app", () => {
  it("de la estantería a las estadísticas y vuelta: los libros se piden una vez y no vuelve el esqueleto", async () => {
    act(() => root.render(<App />));
    await settle();
    expect(host.textContent).toContain("Libro sintético");

    act(() => tab("Estadísticas").click());
    await settle();
    act(() => tab("Estantería").click());

    expect(host.querySelector(".skeleton")).toBeNull();
    expect(host.textContent).toContain("Libro sintético");
    await settle();
    expect(times("GET /api/library/books")).toBe(1);
    expect(times("GET /api/library/stats")).toBe(1);
  });

  it("abrir un libro desde la estantería lo pinta sin esperar a su ficha", async () => {
    replies[`GET /api/library/books/${ID}`] = () => new Promise(() => undefined);
    act(() => root.render(<App />));
    await settle();

    act(() => host.querySelector<HTMLButtonElement>(".media-card-open")!.click());

    expect(window.location.pathname).toBe(`/library/libro/${ID}`);
    expect(host.querySelector(".app-shell-detail h1")?.textContent).toContain("Libro sintético");
    expect(host.querySelector(".app-shell-main")?.textContent).toContain("Tus libros");
    expect(host.textContent).toContain("Terminado hoy");
  });

  it("«Terminado hoy» se ve antes de que conteste, y vuelve atrás si el servidor no lo acepta", async () => {
    let answer!: (response: Response) => void;
    replies[`GET /api/library/books/${ID}`] = () => BOOK;
    replies[`PUT /api/library/books/${ID}`] = () => new Promise<Response>((resolve) => (answer = resolve));
    window.history.replaceState(null, "", `/library/libro/${ID}`);
    act(() => root.render(<App />));
    await settle();

    const finish = Array.from(host.querySelectorAll("button")).find((one) => one.textContent?.includes("Terminado hoy"))!;
    act(() => finish.click());
    await settle();
    expect(host.textContent).toContain("Leído");
    expect(host.textContent).not.toContain("Terminado hoy");

    answer(json({ detail: "leído es con fecha de inicio y de fin" }, 409));
    await settle();
    expect(host.textContent).toContain("Terminado hoy");
    expect(host.textContent).toContain("leído es con fecha de inicio y de fin");
  });
});
