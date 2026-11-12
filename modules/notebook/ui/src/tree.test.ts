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

describe("el árbol", () => {
  it("anida carpetas, cuenta lo de dentro y ordena como el Finder", () => {
    const root = build({
      folders: ["Study", "Study/Alemán"],
      notes: [note("Study/Alemán", "DE 2.10"), note("Study/Alemán", "DE 2.9"), note("", "Suelta")],
    });

    expect(root.count).toBe(3);
    expect(root.folders[0]!.count).toBe(2);
    expect(root.folders[0]!.folders[0]!.notes.map((n) => n.title)).toEqual(["DE 2.9", "DE 2.10"]);
    expect(root.notes.map((n) => n.title)).toEqual(["Suelta"]);
  });

  it("una nota en una carpeta sin fila crea la carpeta", () => {
    expect(build({ folders: [], notes: [note("A/B", "x")] }).folders[0]!.folders[0]!.path).toBe("A/B");
  });

  it("las carpetas de encima", () => {
    expect(ancestors("a/b/c")).toEqual(["a", "a/b", "a/b/c"]);
    expect(ancestors("")).toEqual([]);
  });

  it("filtra por título sin diéresis, primero lo que empieza así", () => {
    const notes = [note("", "Über Präpositionen"), note("", "Präfixe"), note("", "Otra")];

    expect(filter(notes, "pra").map((n) => n.title)).toEqual(["Präfixe", "Über Präpositionen"]);
    expect(filter(notes, "  ")).toEqual([]);
  });
});
