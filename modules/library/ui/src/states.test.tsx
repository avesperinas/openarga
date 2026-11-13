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
  title: "Synthetic book",
  subtitle: null,
  authors: ["Synthetic Author"],
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
  genres: [{ id: "novel", name: "Novel", books: 1, pages: 300 }],
  authors: [{ id: "a", name: "Synthetic Author", books: 1, pages: 300 }],
  ratings: { "4": 1 },
  longest: { id: ID, title: "Synthetic book", pages: 300, days: 20 },
  fastest: { id: ID, title: "Synthetic book", pages: 300, days: 20 },
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
    "GET /api/library/genres": () => [{ id: "novel", name: "Novel" }],
    "GET /api/library/version": () => ({ version: "1.0.0" }),
    "GET /api/library/stats": () => YEAR,
    [`GET /api/library/books/${ID}`]: () => BOOK,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const reply = replies[`${init?.method ?? "GET"} ${url}`];
      if (!reply) return json({ detail: "not found" }, 404);
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

const retry = () => host.querySelector<HTMLButtonElement>('.empty-state[role="alert"] button') ?? undefined;

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

describe("the shelf", () => {
  it("while it arrives, the skeleton", async () => {
    replies["GET /api/library/books"] = () => new Promise(() => undefined);
    await open("/library/");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("empty, it says what to do and the button opens the add sheet", async () => {
    replies["GET /api/library/books"] = () => [];
    await open("/library/");
    expect(host.textContent).toContain("No books yet");

    act(() => button("Add a book")!.click());
    await settle();
    expect(document.querySelector("dialog, [role=dialog]")).not.toBeNull();
  });

  it("if it fails, it says so and retrying brings it", async () => {
    replies["GET /api/library/books"] = () => json({ detail: "the database is not answering" }, 503);
    await open("/library/");
    expect(host.textContent).toContain("Could not read the shelf");
    expect(host.textContent).toContain("the database is not answering");

    replies["GET /api/library/books"] = () => [BOOK];
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).not.toContain("Could not read the shelf");
    expect(host.querySelector('[aria-label="Synthetic book"]')).not.toBeNull();
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open("/library/");
    expect(host.querySelector('.notice[data-tone="warning"]')).not.toBeNull();
  });

  it("axe-core without serious errors", async () => {
    await open("/library/");
    expect(await serious()).toEqual([]);
  });
});

describe("the stats", () => {
  it("a year without books leads to the shelf", async () => {
    replies["GET /api/library/stats"] = () => EMPTY_YEAR;
    await open("/library/stats");
    expect(host.textContent).toContain("Nothing read in 2026");

    act(() => button("Go to the shelf")!.click());
    await settle();
    expect(window.location.pathname).toBe("/library/");
  });

  it("if they fail, retry", async () => {
    replies["GET /api/library/stats"] = () => json({ detail: "no" }, 500);
    await open("/library/stats");
    expect(host.textContent).toContain("Could not read the figures");

    replies["GET /api/library/stats"] = () => YEAR;
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("Pages per month");
  });

  it("axe-core without serious errors", async () => {
    await open("/library/stats");
    expect(host.textContent).toContain("Pages per month");
    expect(await serious()).toEqual([]);
  });
});

describe("the book", () => {
  it("if it cannot be opened, retry", async () => {
    replies["GET /api/library/books"] = () => [];
    replies[`GET /api/library/books/${ID}`] = () => json({ detail: "no" }, 500);
    await open(`/library/books/${ID}`);
    expect(host.textContent).toContain("Could not open the book");

    replies[`GET /api/library/books/${ID}`] = () => BOOK;
    act(() => retry()!.click());
    await settle();
    expect(host.querySelector(".app-shell-detail h1")?.textContent).toContain("Synthetic book");
  });

  it("axe-core without serious errors", async () => {
    await open(`/library/books/${ID}`);
    expect(await serious()).toEqual([]);
  });
});
