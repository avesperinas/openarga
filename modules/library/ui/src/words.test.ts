import { type Book, type Reading, problemOf } from "./api";
import { rowDetail, shelves, splitAuthors, stars, withStatus } from "./words";

function readingOf(overrides: Partial<Reading>): Reading {
  return { status: "want", started_on: null, finished_on: null, rating: null, format: "paper", genre: "other", note: null, ...overrides };
}

function book(overrides: Partial<Book>): Book {
  return {
    id: overrides.title ?? "x",
    edition: "manual",
    edition_id: "e",
    title: "Libro",
    subtitle: null,
    authors: ["Autora Sintética"],
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

describe("los estantes", () => {
  it("lo que lees arriba, lo leído por año del más reciente y lo pendiente al final", () => {
    const found = shelves([
      book({ title: "Viejo", finished_on: "2025-05-01", started_on: "2025-04-01" }),
      book({ title: "Pendiente", status: "want", started_on: null, finished_on: null }),
      book({ title: "Nuevo" }),
      book({ title: "En curso", status: "reading", finished_on: null }),
      book({ title: "Dejado", status: "abandoned", started_on: "2026-03-01", finished_on: null }),
    ]);

    expect(found.map((shelf) => shelf.title)).toEqual(["Leyendo", "2026", "2025", "Quiero leerlos"]);
    expect(found[1]?.books.map((one) => one.title)).toEqual(["Nuevo", "Dejado"]);
  });

  it("sin libros no hay estantes", () => {
    expect(shelves([])).toEqual([]);
  });
});

describe("el estado pone sus fechas", () => {
  const want: Reading = readingOf({ status: "want", started_on: null, finished_on: null });

  it("leído pone inicio y fin con hoy donde falten", () => {
    expect(withStatus(want, "read", "2026-09-25")).toMatchObject({
      status: "read",
      started_on: "2026-09-25",
      finished_on: "2026-09-25",
    });
  });

  it("volver a leyendo quita el fin y conserva el inicio", () => {
    const read = readingOf({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20" });

    expect(withStatus(read, "reading", "2026-09-25")).toMatchObject({
      started_on: "2026-09-01",
      finished_on: null,
    });
  });

  it("quiero leerlo no lleva fechas", () => {
    const read = readingOf({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20" });

    expect(withStatus(read, "want", "2026-09-25")).toMatchObject({ started_on: null, finished_on: null });
  });
});

describe("las palabras", () => {
  it("la fila de un leído dice cuándo y cuánto te gustó", () => {
    expect(rowDetail(book({ finished_on: "2026-09-20", rating: 4.5 }))).toBe("20 sept · ★ 4,5");
  });

  it("los autores se separan por comas y sin huecos", () => {
    expect(splitAuthors(" Una ,, Otra ")).toEqual(["Una", "Otra"]);
  });

  it("sin valoración no hay estrellas", () => {
    expect(stars(null)).toBe("");
  });

  it("el motivo de un 422 es su primera frase, sin el prefijo de pydantic", () => {
    expect(problemOf({ detail: [{ msg: "Value error, leído es con fecha de inicio y de fin" }] })).toBe(
      "leído es con fecha de inicio y de fin",
    );
    expect(problemOf({ detail: "falta cuándo lo empezaste" })).toBe("falta cuándo lo empezaste");
  });
});
