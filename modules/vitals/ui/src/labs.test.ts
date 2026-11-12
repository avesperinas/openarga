import { describe, expect, it } from "vitest";

import { cellShort, cellText, number, parseNumber, rangeText } from "./labs";

const cell = { value: 151, value_text: null, unit: "mg/dL", ref_low: 0, ref_high: 130, out: true };

describe("cómo se lee un valor", () => {
  it("lo que queda fuera lleva flecha, además del color", () => {
    expect(cellText(cell)).toBe("151 ↑");
    expect(cellText({ ...cell, value: 30, ref_low: 40, ref_high: null })).toBe("30 ↓");
    expect(cellText({ ...cell, value: 118, out: false })).toBe("118");
    expect(cellText({ ...cell, value: null, value_text: "Negativo", out: false })).toBe("Negativo");
  });

  it("en la tabla, un texto largo se queda en tres letras y los números no se tocan", () => {
    expect(cellShort({ ...cell, value: null, value_text: "Negativo", out: false })).toBe("Neg.");
    expect(cellShort({ ...cell, value: null, value_text: "Norm", out: false })).toBe("Norm");
    expect(cellShort(cell)).toBe("151 ↑");
  });

  it("el rango se escribe como en un informe", () => {
    expect(rangeText(60, 110, "mg/dL")).toBe("60–110 mg/dL");
    expect(rangeText(0, 130)).toBe("≤ 130");
    expect(rangeText(null, 130)).toBe("≤ 130");
    expect(rangeText(40, null)).toBe("≥ 40");
    expect(rangeText(null, null)).toBe("");
  });

  it("los decimales dependen del tamaño", () => {
    expect(number(4.74)).toBe("4,74");
    expect(number(15.2)).toBe("15,2");
    expect(number(211)).toBe("211");
  });

  it("acepta coma decimal", () => {
    expect(parseNumber("133,5")).toBe(133.5);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("mucho")).toBeNull();
  });
});

describe("la densidad de la orina", () => {
  it("un punto es decimal, no de miles", () => {
    expect(parseNumber("1.010")).toBe(1.01);
  });
});
