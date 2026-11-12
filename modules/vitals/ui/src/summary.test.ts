import { describe, expect, it } from "vitest";

import { changeLine } from "./summary";

describe("la última revisión contra la anterior", () => {
  const ldl = { id: "ldl", name: "Colesterol LDL", panel: "lipidos" as const, unit: "mg/dL", about: "" };

  it("dice cuánto era, cuánto es y si entró o salió de rango", () => {
    const change = { analyte: ldl, value: 150, previous: 120, unit: "mg/dL", change: 30, out: true, was_out: false };
    expect(changeLine(change)).toBe("120 → 150 mg/dL, ahora fuera de rango");
    expect(changeLine({ ...change, out: false, was_out: true })).toBe("120 → 150 mg/dL, vuelve al rango");
    expect(changeLine({ ...change, out: false })).toBe("120 → 150 mg/dL");
  });
});
