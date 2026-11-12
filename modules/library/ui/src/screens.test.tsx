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
    ...overrides,
  };
}

describe("las direcciones", () => {
  it("cada pantalla tiene la suya y vuelve a ella", () => {
    const id = "00000000-0000-4000-8000-000000000001";
    expect(route("/library/")).toEqual({ tab: "shelf" });
    expect(route("/library/estadisticas")).toEqual({ tab: "stats" });
    expect(route(`/library/libro/${id}`)).toEqual({ tab: "book", id });
    expect(route("/library/libro/otra-cosa")).toEqual({ tab: "shelf" });
    expect(pathOf({ tab: "book", id })).toBe(`/library/libro/${id}`);
  });
});

describe("la ficha", () => {
  it("dice las fechas según el estado", () => {
    expect(datesLine(book({}))).toBe("Leído del 1 sept al 20 sept · 20 días");
    expect(datesLine(book({ status: "reading", finished_on: null, days: null }), "2026-09-10")).toBe(
      "Desde el 1 sept · 10 días",
    );
    expect(datesLine(book({ status: "want", started_on: null, finished_on: null }))).toBe("Todavía sin empezar");
  });

  it("sin portada, el título y el autor en su sitio", () => {
    const html = renderToString(<Cover book={book({})} />);

    expect(html).toContain("Libro sintético");
    expect(html).not.toContain("<img");
    expect(renderToString(<Cover book={book({ has_cover: true })} />)).toContain(
      'src="/api/library/books/00000000-0000-4000-8000-000000000001/cover?e=e"',
    );
  });
});

describe("los filtros", () => {
  const books = [
    book({ title: "A", genre: "novel", rating: 5 }),
    book({ title: "B", genre: "history", rating: 3, format: "ebook" }),
    book({ title: "C", genre: "novel", rating: null }),
  ];

  it("por temática, formato y valoración mínima", () => {
    const titles = (filters = NO_FILTERS) => filtered(books, filters).map((one) => one.title);
    expect(titles()).toEqual(["A", "B", "C"]);
    expect(titles({ ...NO_FILTERS, genre: "novel" })).toEqual(["A", "C"]);
    expect(titles({ ...NO_FILTERS, format: "ebook" })).toEqual(["B"]);
    expect(titles({ ...NO_FILTERS, rating: "4" })).toEqual(["A"]);
  });
});

describe("las estadísticas", () => {
  it("el objetivo dice si vas por delante o por detrás", () => {
    expect(goalFoot({ books: 3, goal: null, goal_pace: null })).toBe("sin objetivo");
    expect(goalFoot({ books: 10, goal: 24, goal_pace: 17.9 })).toBe("de 24 · 8 por detrás");
    expect(goalFoot({ books: 18, goal: 24, goal_pace: 17.9 })).toBe("de 24 · vas al día");
    expect(goalFoot({ books: 5, goal: 12, goal_pace: null })).toBe("de 12");
  });

  it("este año contra el anterior (T-B13)", () => {
    expect(change(14, 11, 2025)).toEqual({ text: "+3 que en 2025", direction: "up" });
    expect(change(9, 11, 2025)).toEqual({ text: "−2 que en 2025", direction: "down" });
    expect(change(11, 11, 2025)).toEqual({ text: "igual que en 2025", direction: "flat" });
  });

  it("las valoraciones, de la más alta", () => {
    expect(ratingRows({ "3.5": 1, "5": 2 })).toEqual([
      { label: "★ 5", value: "2 libros" },
      { label: "★ 3,5", value: "1 libro" },
    ]);
  });
});

describe("el catálogo", () => {
  it("lo que se manda al elegir no lleva lo que añadió la búsqueda", () => {
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
    expect(failedNote([{ source: "google_books", reason: "sin clave" }])).toBe("Google Books: sin clave");
  });
});

describe("el calendario de páginas", () => {
  it("cada día hasta hoy, y los que no se leyó son cero", () => {
    const days = yearDays(2026, { "2026-01-02": 30 }, "2026-01-03");

    expect(days).toEqual([
      { day: "2026-01-01", value: 0 },
      { day: "2026-01-02", value: 30 },
      { day: "2026-01-03", value: 0 },
    ]);
    expect(yearDays(2025, {}, "2025-12-31")).toHaveLength(365);
  });
});
