import { describe, expect, it } from "vitest";

import type { NoteSummary } from "./api";
import { ancestors, build, filter } from "./tree";

const note = (folder: string, title: string): NoteSummary => ({
  id: `${folder}/${title}`,
  folder,
  title,
  path: folder ? `${folder}/${title}` : title,
  updated_at: "2026-09-28T10:00:00Z",
  updated_by: "app",
});

describe("the tree", () => {
  it("nests folders, counts what is inside and sorts like the Finder", () => {
    const root = build({
      folders: ["Study", "Study/German"],
      notes: [note("Study/German", "DE 2.10"), note("Study/German", "DE 2.9"), note("", "Loose")],
    });

    expect(root.count).toBe(3);
    expect(root.folders[0]!.count).toBe(2);
    expect(root.folders[0]!.folders[0]!.notes.map((n) => n.title)).toEqual(["DE 2.9", "DE 2.10"]);
    expect(root.notes.map((n) => n.title)).toEqual(["Loose"]);
  });

  it("a note in a folder without a row creates the folder", () => {
    expect(build({ folders: [], notes: [note("A/B", "x")] }).folders[0]!.folders[0]!.path).toBe("A/B");
  });

  it("the folders above", () => {
    expect(ancestors("a/b/c")).toEqual(["a", "a/b", "a/b/c"]);
    expect(ancestors("")).toEqual([]);
  });

  it("filters by title without umlauts, what starts that way first", () => {
    const notes = [note("", "Über Präpositionen"), note("", "Präfixe"), note("", "Other")];

    expect(filter(notes, "pra").map((n) => n.title)).toEqual(["Präfixe", "Über Präpositionen"]);
    expect(filter(notes, "  ")).toEqual([]);
  });
});
