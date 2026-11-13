import { describe, expect, it } from "vitest";

import { english } from "./i18n/testing";
import { against, clock, hours, shortDay, stageSeries, stageShares, timeOf } from "./sleep";

describe("sleep in words", () => {
  it("says hours and minutes", () => {
    expect(hours(437)).toBe("7 h 17 min");
    expect(hours(420)).toBe("7 h");
    expect(hours(9)).toBe("9 min");
    expect(hours(null)).toBe("—");
  });

  it("turns minutes from midnight into a time, also those before", () => {
    expect(clock(-30)).toBe("23:30");
    expect(clock(435)).toBe("07:15");
    expect(clock(null)).toBe("—");
  });

  it("puts the nights short on the axis, in the order of the language", () => {
    expect(shortDay("2026-09-10", "en")).toBe("9/10");
    expect(shortDay("2026-09-10", "es")).toBe("10/9");
  });

  it("takes the time of the instant in the sleeper's time, without converting it", () => {
    expect(timeOf("2026-10-20T07:15:00+02:00")).toBe("07:15");
  });

  it("splits the night into stages, over sleep plus awake", () => {
    expect(stageShares({ stages: { deep: 80, rem: 95, light: 225, awake: 35 } })).toEqual({
      deep: 18,
      rem: 22,
      light: 52,
      awake: 8,
    });
    expect(stageShares({ stages: null })).toEqual({});
  });

  it("gives one series per stage, in hours, for the stacked bars", () => {
    const nights = [{ stages: { deep: 90, rem: 60, light: 240, awake: 30 } }] as never[];
    expect(stageSeries(nights, english).map((one) => [one.key, one.values])).toEqual([
      ["deep", [1.5]],
      ["rem", [1]],
      ["light", [4]],
      ["awake", [0.5]],
    ]);
  });

  it("compares with the average, with its sign", () => {
    expect(against(445, 420, english)).toBe("25 min above your average");
    expect(against(355, 420, english)).toBe("1 h 5 min below your average");
    expect(against(420, 420, english)).toBe("like your average");
    expect(against(420, null, english)).toBe("");
  });
});
