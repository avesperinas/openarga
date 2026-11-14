import { strToU8, zipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { batches, fixName, moved, readVault, unzip } from "./vault";

const nfd = (text: string) => text.normalize("NFD");

function vault(): Record<string, Uint8Array> {
  return unzip(
    zipSync({
      "my-vault/.obsidian/app.json": strToU8("{}"),
      "my-vault/(1).obsidian/app.json": strToU8("{}"),
      "my-vault/.trash/Old.md": strToU8("deleted"),
      [`my-vault/B1 Gramatik/DE 4.2 ${nfd("Wechselpräpositionen")}.md`]: strToU8(
        "\uFEFF---\nthema: x\n---\r\nSee [[DE 1.1 Kasus]] and ![[table.png]] and [[Missing]] and [[training:x]]",
      ),
      "my-vault/B1 Gramatik/DE 1.1 Kasus.md": strToU8(`[[DE 4.2 ${nfd("Wechselpräpositionen")}|w]]`),
      "my-vault/B1 Gramatik/img/table.png": new Uint8Array([1, 2, 3]),
      "my-vault/Ideas.md": strToU8("no folder"),
      "my-vault/data.csv": strToU8("a,b"),
    }).buffer as ArrayBuffer,
  );
}

describe("reading a vault", () => {
  it("drops the outer folder, leaves settings and trash out and composes the names", () => {
    const read = readVault(vault());

    expect(read.notes.map((n) => [n.folder, n.title]).sort()).toEqual([
      ["", "Ideas"],
      ["B1 Gramatik", "DE 1.1 Kasus"],
      ["B1 Gramatik", "DE 4.2 Wechselpräpositionen"],
    ]);
    expect(read.notes.find((n) => n.title.startsWith("DE 4.2"))!.title).toBe("DE 4.2 Wechselpräpositionen".normalize("NFC"));
    expect(read.files.map((f) => f.name)).toEqual(["table.png"]);
    expect(read.left.map((l) => l.path).sort()).toEqual([
      "(1).obsidian/app.json",
      ".obsidian/app.json",
      ".trash/Old.md",
      "data.csv",
    ]);
    expect(read.tops).toEqual(["B1 Gramatik"]);
  });

  it("drops the BOM and Windows line endings", () => {
    const note = readVault(vault()).notes.find((n) => n.title.startsWith("DE 4.2"))!;

    expect(note.content.startsWith("---\nthema: x\n---\nSee")).toBe(true);
  });

  it("says which links find nothing, counting NFD ones and images", () => {
    expect(readVault(vault()).unresolved).toEqual(["Missing"]);
  });

  it("sends a top folder somewhere else", () => {
    const to = { "B1 Gramatik": "/Study/German/B1 Gramatik/" };

    expect(moved("B1 Gramatik", to)).toBe("Study/German/B1 Gramatik");
    expect(moved("B1 Gramatik/Sub", to)).toBe("Study/German/B1 Gramatik/Sub");
    expect(moved("B1 Gramatik", { "B1 Gramatik": "" })).toBe("");
    expect(moved("Other", to)).toBe("Other");
    expect(moved("", to)).toBe("");
  });

  it("fixes UTF-8 names read with another code page on the way", () => {
    const latin = String.fromCharCode(...new TextEncoder().encode("DE 2.1 Präsens.md"));

    expect(latin).not.toBe("DE 2.1 Präsens.md");
    expect(fixName(latin)).toBe("DE 2.1 Präsens.md");
    expect(fixName("DE 2.1 Pr\u251c\u00f1sens.md")).toBe("DE 2.1 Präsens.md");
    expect(fixName("Artikelw\u251c\u00c2rter.md")).toBe("Artikelwörter.md");
    expect(fixName("\u251c\u00a3berblick.md")).toBe("Überblick.md");
    expect(fixName("Crêpe Ölberg.md")).toBe("Crêpe Ölberg.md");
    expect(fixName("Präsens.md")).toBe("Präsens.md");
    expect(fixName("plain.md")).toBe("plain.md");
  });

  it("a note full of zeros does not get in: it says it is empty at the source", () => {
    const read = readVault(unzip(zipSync({ "a.md": new Uint8Array(64), "b.md": strToU8("fine") }).buffer as ArrayBuffer));

    expect(read.notes.map((n) => n.title)).toEqual(["b"]);
    expect(read.left[0]!.reason).toContain("empty at the source");
  });

  it("drops null characters", () => {
    const read = readVault(unzip(zipSync({ "a.md": strToU8("one\u0000two") }).buffer as ArrayBuffer));

    expect(read.notes[0]!.content).toBe("onetwo");
  });

  it("splits in batches", () => {
    expect(batches([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
  });
});
