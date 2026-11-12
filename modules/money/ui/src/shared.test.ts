import { describe, expect, it } from "vitest";

import { keptLine } from "./Shared";

describe("lo común en espejo", () => {
  it("dice quién lo lleva y de cuándo son sus cifras", () => {
    const now = new Date();
    now.setHours(9, 5, 0, 0);
    expect(keptLine({ other: "Uno", kept_at: now.toISOString() })).toBe(
      "Lo lleva Uno en su Money · al día a las 09:05. Lo que apuntes entra en el saldo en medio minuto.",
    );
  });

  it("sin cifras todavía, solo quién", () => {
    expect(keptLine({ other: "Uno", kept_at: null })).toBe("Lo lleva Uno en su Money.");
  });
});
