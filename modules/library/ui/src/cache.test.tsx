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
  title: "Synthetic book",
  subtitle: null,
  authors: ["Synthetic Author"],
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
      if (!reply) return json({ detail: "not found" }, 404);
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

describe("Library with the app kit", () => {
  it("from the shelf to the stats and back: books are asked for once and the skeleton does not come back", async () => {
    act(() => root.render(<App />));
    await settle();
    expect(host.textContent).toContain("Synthetic book");

    act(() => tab("Stats").click());
    await settle();
    act(() => tab("Shelf").click());

    expect(host.querySelector(".skeleton")).toBeNull();
    expect(host.textContent).toContain("Synthetic book");
    await settle();
    expect(times("GET /api/library/books")).toBe(1);
    expect(times("GET /api/library/stats")).toBe(1);
  });

  it("opening a book from the shelf paints it without waiting for its record", async () => {
    replies[`GET /api/library/books/${ID}`] = () => new Promise(() => undefined);
    act(() => root.render(<App />));
    await settle();

    act(() => host.querySelector<HTMLButtonElement>(".media-card-open")!.click());

    expect(window.location.pathname).toBe(`/library/books/${ID}`);
    expect(host.querySelector(".app-shell-detail h1")?.textContent).toContain("Synthetic book");
    expect(host.querySelector(".app-shell-main")?.textContent).toContain("Your books");
    expect(host.textContent).toContain("Finished today");
  });

  it("“Finished today” shows before the answer, and goes back if the server refuses it", async () => {
    let answer!: (response: Response) => void;
    replies[`GET /api/library/books/${ID}`] = () => BOOK;
    replies[`PUT /api/library/books/${ID}`] = () => new Promise<Response>((resolve) => (answer = resolve));
    window.history.replaceState(null, "", `/library/books/${ID}`);
    act(() => root.render(<App />));
    await settle();

    const finish = Array.from(host.querySelectorAll("button")).find((one) => one.textContent?.includes("Finished today"))!;
    act(() => finish.click());
    await settle();
    expect(host.querySelector(".app-shell-detail")?.textContent).toContain("Read");
    expect(host.textContent).not.toContain("Finished today");

    answer(json({ detail: "read has a start date and an end date" }, 409));
    await settle();
    expect(host.textContent).toContain("Finished today");
    expect(host.textContent).toContain("read has a start date and an end date");
  });
});
