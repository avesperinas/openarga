import { describe, expect, it } from "vitest";

import { freeTitle } from "./App";
import { pastedName } from "./NoteEditor";
import { fromText, toText } from "./Properties";

describe("editar", () => {
  it("una nota nueva busca un título libre en su carpeta", () => {
    const note = (folder: string, title: string) => ({ id: title, folder, title, path: title, updated_at: "", updated_by: "app" as const });
    const tree = { folders: ["A"], notes: [note("A", "Sin título"), note("A", "Sin título 2"), note("", "Sin título")] };

    expect(freeTitle(tree, "A")).toBe("Sin título 3");
    expect(freeTitle(tree, "B")).toBe("Sin título");
  });

  it("una imagen pegada se llama como en Obsidian", () => {
    const file = new File([new Uint8Array([1])], "image.png", { type: "image/png" });

    expect(pastedName(file, new Date(2026, 8, 28, 17, 30, 12))).toBe("Pasted image 20260928173012.png");
  });

  it("una propiedad conserva su tipo al escribirla", () => {
    expect(fromText("a, b ,c", ["x"])).toEqual(["a", "b", "c"]);
    expect(fromText("0,25", 0.2)).toBe(0.25);
    expect(fromText("abc", 0.2)).toBe("abc");
    expect(fromText(" texto ", "x")).toBe("texto");
    expect(toText(["a", "b"])).toBe("a, b");
  });
});
