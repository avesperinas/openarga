import { describe, expect, it } from "vitest";

import { english } from "./i18n/testing";
import { changeLine } from "./summary";

describe("the last check-up against the previous one", () => {
  const ldl = { id: "ldl", name: "LDL cholesterol", panel: "lipids" as const, unit: "mg/dL", about: "" };

  it("says what it was, what it is and whether it entered or left the range", () => {
    const change = { analyte: ldl, value: 150, previous: 120, unit: "mg/dL", change: 30, out: true, was_out: false };
    expect(changeLine(change, english, "en")).toBe("120 → 150 mg/dL, now out of range");
    expect(changeLine({ ...change, out: false, was_out: true }, english, "en")).toBe("120 → 150 mg/dL, back in range");
    expect(changeLine({ ...change, out: false }, english, "en")).toBe("120 → 150 mg/dL");
  });
});
