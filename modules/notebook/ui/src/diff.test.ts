import { describe, expect, it } from "vitest";

import { diff, hunks } from "./diff";

describe("qué cambió", () => {
  it("marca lo añadido y lo quitado entre líneas iguales", () => {
    expect(diff("a\nb\nc", "a\nB\nc\nd")).toEqual([
      { op: "same", text: "a" },
      { op: "del", text: "b" },
      { op: "add", text: "B" },
      { op: "same", text: "c" },
      { op: "add", text: "d" },
    ]);
  });

  it("dos versiones iguales no tienen cambios", () => {
    expect(diff("x\ny", "x\ny").every((line) => line.op === "same")).toBe(true);
  });

  it("recorta lo igual lejos de los cambios", () => {
    const before = Array.from({ length: 20 }, (_, i) => `l${i}`).join("\n");
    const after = before.replace("l10", "cambio");

    const shown = hunks(diff(before, after));

    expect(shown[0]).toBeNull();
    expect(shown.filter(Boolean).map((line) => line!.text)).toEqual(["l8", "l9", "l10", "cambio", "l11", "l12"]);
    expect(shown[shown.length - 1]).toBeNull();
  });
});
