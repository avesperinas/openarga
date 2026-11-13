import { missingKeys } from "@openarga/ui";
import { afterEach } from "vitest";

import { type Book, type Reading, problemOf } from "./api";
import { CATALOGS, setLocale } from "./lang";
import { rowDetail, shelves, splitAuthors, stars, statusName, withStatus } from "./words";

function readingOf(overrides: Partial<Reading>): Reading {
  return { status: "want", started_on: null, finished_on: null, rating: null, format: "paper", genre: "other", note: null, ...overrides };
}

function book(overrides: Partial<Book>): Book {
  return {
    id: overrides.title ?? "x",
    edition: "manual",
    edition_id: "e",
    title: "Book",
    subtitle: null,
    authors: ["Synthetic Author"],
    pages: 200,
    language: "es",
    year: 2020,
    isbn13: null,
    has_cover: false,
    source: "app",
    days: null,
    status: "read",
    started_on: "2026-01-01",
    finished_on: "2026-01-10",
    rating: null,
    format: "paper",
    genre: "novel",
    note: null,
    ...overrides,
  };
}

describe("the shelves", () => {
  it("what you read on top, what you read by year newest first, and the pending ones last", () => {
    const found = shelves([
      book({ title: "Old", finished_on: "2025-05-01", started_on: "2025-04-01" }),
      book({ title: "Pending", status: "want", started_on: null, finished_on: null }),
      book({ title: "New" }),
      book({ title: "Ongoing", status: "reading", finished_on: null }),
      book({ title: "Dropped", status: "abandoned", started_on: "2026-03-01", finished_on: null }),
    ]);

    expect(found.map((shelf) => shelf.title)).toEqual(["Reading", "2026", "2025", "Want to read"]);
    expect(found[1]?.books.map((one) => one.title)).toEqual(["New", "Dropped"]);
  });

  it("no books, no shelves", () => {
    expect(shelves([])).toEqual([]);
  });
});

describe("the status sets its dates", () => {
  const want: Reading = readingOf({ status: "want", started_on: null, finished_on: null });

  it("read sets start and end with today where missing", () => {
    expect(withStatus(want, "read", "2026-09-25")).toMatchObject({
      status: "read",
      started_on: "2026-09-25",
      finished_on: "2026-09-25",
    });
  });

  it("back to reading drops the end and keeps the start", () => {
    const read = readingOf({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20" });

    expect(withStatus(read, "reading", "2026-09-25")).toMatchObject({
      started_on: "2026-09-01",
      finished_on: null,
    });
  });

  it("want to read has no dates", () => {
    const read = readingOf({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20" });

    expect(withStatus(read, "want", "2026-09-25")).toMatchObject({ started_on: null, finished_on: null });
  });
});

describe("the words", () => {
  it("a read book's row says when and how much you liked it", () => {
    expect(rowDetail(book({ finished_on: "2026-09-20", rating: 4.5 }))).toBe("20 sept · ★ 4.5");
  });

  it("authors are split by commas without gaps", () => {
    expect(splitAuthors(" One ,, Other ")).toEqual(["One", "Other"]);
  });

  it("no rating, no stars", () => {
    expect(stars(null)).toBe("");
  });

  it("a 422's reason is its first sentence, without pydantic's prefix", () => {
    expect(problemOf({ detail: [{ msg: "Value error, read has a start date and an end date" }] })).toBe(
      "read has a start date and an end date",
    );
    expect(problemOf({ detail: "when you started it is missing" })).toBe("when you started it is missing");
  });
});

describe("the language", () => {
  afterEach(() => setLocale("en"));

  it("both catalogs have the same keys", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("follows the person's locale", () => {
    setLocale("es");
    expect(statusName("read")).toBe(CATALOGS.es!["status.read"]);
    setLocale("en");
    expect(statusName("read")).toBe("Read");
  });
});
