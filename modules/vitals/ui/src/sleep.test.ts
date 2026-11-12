import { describe, expect, it } from "vitest";

import { against, clock, hours, shortDay, stageSeries, stageShares, timeOf } from "./sleep";

describe("el sueño en palabras", () => {
  it("dice las horas y los minutos", () => {
    expect(hours(437)).toBe("7 h 17 min");
    expect(hours(420)).toBe("7 h");
    expect(hours(9)).toBe("9 min");
    expect(hours(null)).toBe("—");
  });

  it("pone en hora los minutos desde medianoche, también los de antes", () => {
    expect(clock(-30)).toBe("23:30");
    expect(clock(435)).toBe("07:15");
    expect(clock(null)).toBe("—");
  });

  it("pone las noches cortas en el eje", () => {
    expect(shortDay("2026-09-10")).toBe("10/9");
  });

  it("toma la hora del instante en la hora de quien durmió, sin convertirla", () => {
    expect(timeOf("2026-10-20T07:15:00+02:00")).toBe("07:15");
  });

  it("reparte la noche en fases, sobre lo dormido más lo despierto", () => {
    expect(stageShares({ stages: { deep: 80, rem: 95, light: 225, awake: 35 } })).toEqual({
      deep: 18,
      rem: 22,
      light: 52,
      awake: 8,
    });
    expect(stageShares({ stages: null })).toEqual({});
  });

  it("da una serie por fase, en horas, para las barras apiladas", () => {
    const nights = [{ stages: { deep: 90, rem: 60, light: 240, awake: 30 } }] as never[];
    expect(stageSeries(nights).map((one) => [one.key, one.values])).toEqual([
      ["deep", [1.5]],
      ["rem", [1]],
      ["light", [4]],
      ["awake", [0.5]],
    ]);
  });

  it("compara con la media, con su signo", () => {
    expect(against(445, 420)).toBe("25 min sobre tu media");
    expect(against(355, 420)).toBe("1 h 5 min bajo tu media");
    expect(against(420, 420)).toBe("como tu media");
    expect(against(420, null)).toBe("");
  });
});
