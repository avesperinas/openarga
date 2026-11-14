import { describe, expect, it } from "vitest";

import { freeTitle } from "./App";
import { pastedName } from "./NoteEditor";
import { fromText, toText } from "./Properties";

describe("editing", () => {
  it("a new note looks for a free title in its folder", () => {
    const note = (folder: string, title: string) => ({ id: title, folder, title, path: title, updated_at: "", updated_by: "app" as const });
    const tree = { folders: ["A"], notes: [note("A", "Untitled"), note("A", "Untitled 2"), note("", "Untitled")] };

    expect(freeTitle(tree, "A")).toBe("Untitled 3");
    expect(freeTitle(tree, "B")).toBe("Untitled");
  });

  it("a pasted image is named as in Obsidian", () => {
    const file = new File([new Uint8Array([1])], "image.png", { type: "image/png" });

    expect(pastedName(file, new Date(2026, 8, 28, 17, 30, 12))).toBe("Pasted image 20260928173012.png");
  });

  it("a property keeps its type when written", () => {
    expect(fromText("a, b ,c", ["x"])).toEqual(["a", "b", "c"]);
    expect(fromText("0,25", 0.2)).toBe(0.25);
    expect(fromText("abc", 0.2)).toBe("abc");
    expect(fromText(" text ", "x")).toBe("text");
    expect(toText(["a", "b"])).toBe("a, b");
  });
});
