import { describe, expect, it } from "vitest";

import { diff, hunks } from "./diff";

describe("what changed", () => {
  it("marks what was added and removed between equal lines", () => {
    expect(diff("a\nb\nc", "a\nB\nc\nd")).toEqual([
      { op: "same", text: "a" },
      { op: "remove", text: "b" },
      { op: "add", text: "B" },
      { op: "same", text: "c" },
      { op: "add", text: "d" },
    ]);
  });

  it("two equal versions have no changes", () => {
    expect(diff("x\ny", "x\ny").every((line) => line.op === "same")).toBe(true);
  });

  it("trims what is equal far from the changes", () => {
    const before = Array.from({ length: 20 }, (_, i) => `l${i}`).join("\n");
    const after = before.replace("l10", "cambio");

    const shown = hunks(diff(before, after));

    expect(shown[0]).toBeNull();
    expect(shown.filter(Boolean).map((line) => line!.text)).toEqual(["l8", "l9", "l10", "cambio", "l11", "l12"]);
    expect(shown[shown.length - 1]).toBeNull();
  });
});
