import { describe, expect, it } from "vitest";

import { cellShort, cellText, number, parseNumber, rangeText } from "./labs";

const cell = { value: 151, value_text: null, unit: "mg/dL", ref_low: 0, ref_high: 130, out: true };

describe("how a value reads", () => {
  it("what falls outside carries an arrow, besides the colour", () => {
    expect(cellText(cell, "en")).toBe("151 ↑");
    expect(cellText({ ...cell, value: 30, ref_low: 40, ref_high: null }, "en")).toBe("30 ↓");
    expect(cellText({ ...cell, value: 118, out: false }, "en")).toBe("118");
    expect(cellText({ ...cell, value: null, value_text: "Negative", out: false }, "en")).toBe("Negative");
  });

  it("in the table, a long text stays at three letters and numbers are untouched", () => {
    expect(cellShort({ ...cell, value: null, value_text: "Negative", out: false }, "en")).toBe("Neg.");
    expect(cellShort({ ...cell, value: null, value_text: "Norm", out: false }, "en")).toBe("Norm");
    expect(cellShort(cell, "en")).toBe("151 ↑");
  });

  it("the range is written like in a report", () => {
    expect(rangeText(60, 110, "en", "mg/dL")).toBe("60–110 mg/dL");
    expect(rangeText(0, 130, "en")).toBe("≤ 130");
    expect(rangeText(null, 130, "en")).toBe("≤ 130");
    expect(rangeText(40, null, "en")).toBe("≥ 40");
    expect(rangeText(null, null, "en")).toBe("");
  });

  it("the decimals depend on the size, and the mark on the language", () => {
    expect(number(4.74, "en")).toBe("4.74");
    expect(number(15.2, "en")).toBe("15.2");
    expect(number(211, "en")).toBe("211");
    expect(number(4.74, "es")).toBe("4,74");
  });

  it("accepts a decimal comma", () => {
    expect(parseNumber("133,5")).toBe(133.5);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("a lot")).toBeNull();
  });
});

describe("urine specific gravity", () => {
  it("a dot is a decimal, not thousands", () => {
    expect(parseNumber("1.010")).toBe(1.01);
  });
});
