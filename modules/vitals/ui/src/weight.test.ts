import { describe, expect, it } from "vitest";

import type { Day } from "./api";
import { bandFoot, bandLabel, changeTone, extremes, inPeriod, monthsBefore, parseKg, today } from "./weight";

const day = (date: string, kg: number): Day => ({ day: date, kg, avg7: kg });
const noGoal = { steps_per_day: null, weight_min_kg: null, weight_max_kg: null, weight_direction: null };

describe("el periodo", () => {
  const days = [day("2025-06-01", 84), day("2026-06-15", 81), day("2026-07-01", 80), day("2026-09-20", 79)];

  it("cuenta hacia atrás desde la última pesada", () => {
    expect(inPeriod(days, "3m").map((one) => one.day)).toEqual(["2026-07-01", "2026-09-20"]);
    expect(inPeriod(days, "1y")).toHaveLength(3);
    expect(inPeriod(days, "all")).toHaveLength(4);
    expect(inPeriod([], "3m")).toEqual([]);
  });

  it("resta meses de calendario", () => {
    expect(monthsBefore("2026-09-20", 3)).toBe("2026-06-20");
    expect(monthsBefore("2026-02-10", 12)).toBe("2025-02-10");
  });

  it("dice el día más ligero y el más pesado", () => {
    expect(extremes(days)).toEqual({ min: days[3], max: days[0] });
    expect(extremes([])).toBeNull();
  });
});

describe("contra el objetivo", () => {
  it("bajar es bueno por encima de la banda y malo por debajo", () => {
    expect(changeTone(-1.2, "above")).toBe("positive");
    expect(changeTone(0.8, "above")).toBe("negative");
    expect(changeTone(0.8, "below")).toBe("positive");
    expect(changeTone(-1.2, null)).toBe("neutral");
    expect(changeTone(null, "above")).toBe("neutral");
  });

  it("dice en kilos cuánto falta, y la banda como se lee", () => {
    const band = { steps_per_day: null, weight_min_kg: 72, weight_max_kg: 76, weight_direction: null };

    expect(bandFoot(78.5, band, "above")).toBe("2,5 kg por encima del objetivo");
    expect(bandFoot(74, band, "inside")).toBe("Dentro del objetivo");
    expect(bandFoot(74, noGoal, null)).toBe("Sin objetivo");
    expect(bandLabel(band)).toBe("Entre 72,0 kg y 76,0 kg");
    expect(bandLabel({ ...noGoal, weight_max_kg: 76 })).toBe("Hasta 76,0 kg");
  });
});

describe("lo que se teclea", () => {
  it("acepta coma o punto y rechaza lo que no es un peso", () => {
    expect(parseKg("78,4")).toBe(78.4);
    expect(parseKg(" 78.4 ")).toBe(78.4);
    expect(parseKg("8,1")).toBeNull();
    expect(parseKg("mucho")).toBeNull();
  });

  it("hoy es hoy en Madrid", () => {
    expect(today(new Date("2026-09-25T22:30:00Z"))).toBe("2026-09-26");
  });
});
