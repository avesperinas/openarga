import { strToU8, zipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { batches, fixName, moved, readVault, unzip } from "./vault";

const nfd = (text: string) => text.normalize("NFD");

function vault(): Record<string, Uint8Array> {
  return unzip(
    zipSync({
      "mi-vault/.obsidian/app.json": strToU8("{}"),
      "mi-vault/(1).obsidian/app.json": strToU8("{}"),
      "mi-vault/.trash/Vieja.md": strToU8("borrada"),
      [`mi-vault/B1 Gramatik/DE 4.2 ${nfd("Wechselpräpositionen")}.md`]: strToU8(
        "\uFEFF---\nthema: x\n---\r\nVer [[DE 1.1 Kasus]] y ![[tabla.png]] y [[Falta]] y [[training:x]]",
      ),
      "mi-vault/B1 Gramatik/DE 1.1 Kasus.md": strToU8(`[[DE 4.2 ${nfd("Wechselpräpositionen")}|w]]`),
      "mi-vault/B1 Gramatik/img/tabla.png": new Uint8Array([1, 2, 3]),
      "mi-vault/Ideas.md": strToU8("sin carpeta"),
      "mi-vault/datos.csv": strToU8("a,b"),
    }).buffer as ArrayBuffer,
  );
}

describe("leer un vault", () => {
  it("quita la carpeta de fuera, deja la configuración y la papelera y compone los nombres", () => {
    const read = readVault(vault());

    expect(read.notes.map((n) => [n.folder, n.title]).sort()).toEqual([
      ["", "Ideas"],
      ["B1 Gramatik", "DE 1.1 Kasus"],
      ["B1 Gramatik", "DE 4.2 Wechselpräpositionen"],
    ]);
    expect(read.notes.find((n) => n.title.startsWith("DE 4.2"))!.title).toBe("DE 4.2 Wechselpräpositionen".normalize("NFC"));
    expect(read.files.map((f) => f.name)).toEqual(["tabla.png"]);
    expect(read.left.map((l) => l.path).sort()).toEqual([
      "(1).obsidian/app.json",
      ".obsidian/app.json",
      ".trash/Vieja.md",
      "datos.csv",
    ]);
    expect(read.tops).toEqual(["B1 Gramatik"]);
  });

  it("quita el BOM y los finales de línea de Windows", () => {
    const note = readVault(vault()).notes.find((n) => n.title.startsWith("DE 4.2"))!;

    expect(note.content.startsWith("---\nthema: x\n---\nVer")).toBe(true);
  });

  it("dice qué enlaces no encuentran nada, contando los de NFD y las imágenes", () => {
    expect(readVault(vault()).unresolved).toEqual(["Falta"]);
  });

  it("manda una carpeta de arriba a otro sitio", () => {
    const to = { "B1 Gramatik": "/Study/Alemán/B1 Gramatik/" };

    expect(moved("B1 Gramatik", to)).toBe("Study/Alemán/B1 Gramatik");
    expect(moved("B1 Gramatik/Sub", to)).toBe("Study/Alemán/B1 Gramatik/Sub");
    expect(moved("B1 Gramatik", { "B1 Gramatik": "" })).toBe("");
    expect(moved("Otra", to)).toBe("Otra");
    expect(moved("", to)).toBe("");
  });

  it("arregla los nombres UTF-8 leídos con otra tabla por el camino", () => {
    const latin = String.fromCharCode(...new TextEncoder().encode("DE 2.1 Präsens.md"));

    expect(latin).not.toBe("DE 2.1 Präsens.md");
    expect(fixName(latin)).toBe("DE 2.1 Präsens.md");
    expect(fixName("DE 2.1 Pr\u251c\u00f1sens.md")).toBe("DE 2.1 Präsens.md");
    expect(fixName("Artikelw\u251c\u00c2rter.md")).toBe("Artikelwörter.md");
    expect(fixName("\u251c\u00a3berblick.md")).toBe("Überblick.md");
    expect(fixName("Ñandú.md")).toBe("Ñandú.md");
    expect(fixName("Präsens.md")).toBe("Präsens.md");
    expect(fixName("plain.md")).toBe("plain.md");
  });

  it("una nota llena de ceros no entra: se dice que está vacía en el origen", () => {
    const read = readVault(unzip(zipSync({ "a.md": new Uint8Array(64), "b.md": strToU8("bien") }).buffer as ArrayBuffer));

    expect(read.notes.map((n) => n.title)).toEqual(["b"]);
    expect(read.left[0]!.reason).toContain("vacía en el origen");
  });

  it("quita los caracteres nulos", () => {
    const read = readVault(unzip(zipSync({ "a.md": strToU8("uno\u0000dos") }).buffer as ArrayBuffer));

    expect(read.notes[0]!.content).toBe("unodos");
  });

  it("parte en tandas", () => {
    expect(batches([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
  });
});
