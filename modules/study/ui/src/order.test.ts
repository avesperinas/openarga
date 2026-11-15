import { defaultTracks } from "./CourseSheet";
import { codeColumn, neighbours, reading, resolver, splitCode } from "./order";

describe("the order of notes", () => {
  it("splits the number of a series from its name", () => {
    expect(splitCode("DE 1.1 Kasus - Funktionen im Überblick")).toEqual({
      prefix: "DE",
      number: "1.1",
      name: "Kasus - Funktionen im Überblick",
    });
    expect(splitCode("3. Derivadas")).toEqual({ prefix: "", number: "3", name: "Derivadas" });
    expect(splitCode("Clase del 2026-09-28")).toBeNull();
    expect(splitCode("Verbos fuertes")).toBeNull();
  });

  it("drops the series column when the whole list shares it", () => {
    expect(codeColumn(["DE 1.1 Kasus", "DE 1.2 Artikel", "Notas"])).toEqual(["1.1", "1.2", null]);
    expect(codeColumn(["DE 1.1 Kasus", "EN 1.1 Tenses"])).toEqual(["DE 1.1", "EN 1.1"]);
  });

  it("finds the previous and the next in the same folder, in natural order", () => {
    const note = (id: string, title: string, folder = "B1") => ({ id, title, folder, session_id: null });
    const notes = [note("c", "DE 1.10 c"), note("a", "DE 1.2 a"), note("b", "DE 1.9 b"), note("x", "Otra", "Otra")];

    expect(neighbours(notes, { id: "b", folder: "B1" })).toEqual({ previous: notes[1], next: notes[0] });
    expect(neighbours(notes, { id: "x", folder: "Otra" })).toEqual({ previous: null, next: null });
  });

  it("counts words and minutes without counting the marks", () => {
    expect(reading("## Kern\n\n| a | b |\n|---|---|\n**Der Mann** schläft.")).toEqual({ words: 6, minutes: 1 });
  });
});

describe("the links between notes", () => {
  it("find the note by its name, with or without a folder", () => {
    const resolve = resolver([{ id: "a", title: "DE 1.2 Artikelwörter" }]);

    expect(resolve("DE 1.2 Artikelwörter")).toBe("a");
    expect(resolve("Study/German/B1 Grammatik/de 1.2 artikelwörter.md")).toBe("a");
    expect(resolve("DE 9.9 Otra")).toBeNull();
  });
});

describe("what is tracked for a course", () => {
  it("a language starts with no figures and a master with all three", () => {
    expect(defaultTracks("language")).toEqual([]);
    expect(defaultTracks("master")).toEqual(["grades", "progress", "attendance"]);
  });
});
