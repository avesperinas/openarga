import { renderToString } from "react-dom/server";

import { pathOf, route } from "./App";
import { type Book, type FoundCandidate, asCandidate } from "./api";
import { Cover } from "./Cover";
import { change } from "./Stats";
import { NO_FILTERS, datesLine, failedNote, filtered, goalFoot, ratingRows, yearDays } from "./words";

function book(overrides: Partial<Book>): Book {
  return {
    id: "00000000-0000-4000-8000-000000000001",
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
    ...overrides,
  };
}

describe("the routes", () => {
  it("each screen has its own and comes back to it", () => {
    const id = "00000000-0000-4000-8000-000000000001";
    expect(route("/library/")).toEqual({ tab: "shelf" });
    expect(route("/library/stats")).toEqual({ tab: "stats" });
    expect(route(`/library/books/${id}`)).toEqual({ tab: "book", id });
    expect(route("/library/books/something-else")).toEqual({ tab: "shelf" });
    expect(pathOf({ tab: "book", id })).toBe(`/library/books/${id}`);
  });
});

describe("the book", () => {
  it("says the dates by status", () => {
    expect(datesLine(book({}))).toBe("Read 1 sept to 20 sept · 20 days");
    expect(datesLine(book({ status: "reading", finished_on: null, days: null }), "2026-09-10")).toBe(
      "Since 1 sept · 10 days",
    );
    expect(datesLine(book({ status: "want", started_on: null, finished_on: null }))).toBe("Not started yet");
  });

  it("without a cover, the title and author take its place", () => {
    const html = renderToString(<Cover book={book({})} />);

    expect(html).toContain("Synthetic book");
    expect(html).not.toContain("<img");
    expect(renderToString(<Cover book={book({ has_cover: true })} />)).toContain(
      'src="/api/library/books/00000000-0000-4000-8000-000000000001/cover?e=e"',
    );
  });
});

describe("the filters", () => {
  const books = [
    book({ title: "A", genre: "novel", rating: 5 }),
    book({ title: "B", genre: "history", rating: 3, format: "ebook" }),
    book({ title: "C", genre: "novel", rating: null }),
  ];

  it("by genre, format and minimum rating", () => {
    const titles = (filters = NO_FILTERS) => filtered(books, filters).map((one) => one.title);
    expect(titles()).toEqual(["A", "B", "C"]);
    expect(titles({ ...NO_FILTERS, genre: "novel" })).toEqual(["A", "C"]);
    expect(titles({ ...NO_FILTERS, format: "ebook" })).toEqual(["B"]);
    expect(titles({ ...NO_FILTERS, rating: "4" })).toEqual(["A"]);
  });
});

describe("the stats", () => {
  it("the goal says whether you are ahead or behind", () => {
    expect(goalFoot({ books: 3, goal: null, goal_pace: null })).toBe("no goal");
    expect(goalFoot({ books: 10, goal: 24, goal_pace: 17.9 })).toBe("of 24 · 8 behind");
    expect(goalFoot({ books: 18, goal: 24, goal_pace: 17.9 })).toBe("of 24 · on pace");
    expect(goalFoot({ books: 5, goal: 12, goal_pace: null })).toBe("of 12");
  });

  it("this year against the last (T-B13)", () => {
    expect(change(14, 11, 2025)).toEqual({ text: "+3 on 2025", direction: "up" });
    expect(change(9, 11, 2025)).toEqual({ text: "−2 on 2025", direction: "down" });
    expect(change(11, 11, 2025)).toEqual({ text: "same as in 2025", direction: "flat" });
  });

  it("the ratings, highest first", () => {
    expect(ratingRows({ "3.5": 1, "5": 2 })).toEqual([
      { label: "★ 5", value: "2 books" },
      { label: "★ 3.5", value: "1 book" },
    ]);
  });
});

describe("the catalog", () => {
  it("what is sent on choosing leaves out what the search added", () => {
    const found: FoundCandidate = {
      source: "openlibrary",
      source_ref: "OL1M",
      title: "T",
      subtitle: null,
      authors: [],
      isbn13: null,
      pages: null,
      language: null,
      year: null,
      subjects: [],
      cover_ref: null,
      genre_hint: "novel",
      known_id: null,
    };

    expect(Object.keys(asCandidate(found))).not.toContain("genre_hint");
    expect(failedNote([{ source: "google_books", reason: "no key" }])).toBe("Google Books: no key");
  });
});

describe("the pages calendar", () => {
  it("every day until today, and days without reading are zero", () => {
    const days = yearDays(2026, { "2026-01-02": 30 }, "2026-01-03");

    expect(days).toEqual([
      { day: "2026-01-01", value: 0 },
      { day: "2026-01-02", value: 30 },
      { day: "2026-01-03", value: 0 },
    ]);
    expect(yearDays(2025, {}, "2025-12-31")).toHaveLength(365);
  });
});
