import { defaultTracks } from "./CourseSheet";
import { codeColumn, neighbours, reading, resolver, splitCode } from "./order";

describe("el orden de los apuntes", () => {
  it("separa el número de una serie de su nombre", () => {
    expect(splitCode("DE 1.1 Kasus - Funktionen im Überblick")).toEqual({
      prefix: "DE",
      number: "1.1",
      name: "Kasus - Funktionen im Überblick",
    });
    expect(splitCode("3. Derivadas")).toEqual({ prefix: "", number: "3", name: "Derivadas" });
    expect(splitCode("Clase del 2026-09-28")).toBeNull();
    expect(splitCode("Verbos fuertes")).toBeNull();
  });

  it("quita la serie de la columna si toda la lista es de la misma", () => {
    expect(codeColumn(["DE 1.1 Kasus", "DE 1.2 Artikel", "Notas"])).toEqual(["1.1", "1.2", null]);
    expect(codeColumn(["DE 1.1 Kasus", "EN 1.1 Tenses"])).toEqual(["DE 1.1", "EN 1.1"]);
  });

  it("encuentra el anterior y el siguiente en la misma carpeta, en orden natural", () => {
    const note = (id: string, title: string, folder = "B1") => ({ id, title, folder, session_id: null });
    const notes = [note("c", "DE 1.10 c"), note("a", "DE 1.2 a"), note("b", "DE 1.9 b"), note("x", "Otra", "Otra")];

    expect(neighbours(notes, { id: "b", folder: "B1" })).toEqual({ previous: notes[1], next: notes[0] });
    expect(neighbours(notes, { id: "x", folder: "Otra" })).toEqual({ previous: null, next: null });
  });

  it("cuenta palabras y minutos sin contar las marcas", () => {
    expect(reading("## Kern\n\n| a | b |\n|---|---|\n**Der Mann** schläft.")).toEqual({ words: 6, minutes: 1 });
  });
});

describe("los enlaces entre apuntes", () => {
  it("encuentran la nota por su nombre, con o sin carpeta", () => {
    const resolve = resolver([{ id: "a", title: "DE 1.2 Artikelwörter" }]);

    expect(resolve("DE 1.2 Artikelwörter")).toBe("a");
    expect(resolve("Study/Alemán/B1 Gramatik/de 1.2 artikelwörter.md")).toBe("a");
    expect(resolve("DE 9.9 Otra")).toBeNull();
  });
});

describe("qué se sigue de un estudio", () => {
  it("un idioma nace sin cifras y un máster con las tres", () => {
    expect(defaultTracks("language")).toEqual([]);
    expect(defaultTracks("master")).toEqual(["grades", "progress", "attendance"]);
  });
});
