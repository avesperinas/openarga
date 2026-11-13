import { describe, expect, it } from "vitest";

import { heartSeries, minuteLabel, heartSummary } from "./heart";
import { english } from "./i18n/testing";

describe("the heart rate curve", () => {
  it("names each span by its time", () => {
    expect(minuteLabel(0)).toBe("00:00");
    expect(minuteLabel(485)).toBe("08:05");
  });

  it("gives the maximum, average and minimum of each span", () => {
    const series = heartSeries([
      { minute: 480, min: 55, avg: 58, max: 63 },
      { minute: 485, min: 60, avg: 75, max: 92 },
    ], english);
    expect(series.map((one) => [one.key, one.values])).toEqual([
      ["max", [63, 92]],
      ["avg", [58, 75]],
      ["min", [55, 60]],
    ]);
  });
});

describe("the heart over time", () => {
  it("compares the average now with a month ago and finds the lowest", () => {
    const points = Array.from({ length: 60 }, (_, index) => {
      const day = new Date(Date.UTC(2026, 7, 16 + index)).toISOString().slice(0, 10);
      return { day, value: index < 30 ? 60 : 55 };
    });
    const found = heartSummary(
      {
        figure: { id: "resting_heart_rate", group: "heart", name: "Resting HR", unit: "bpm", digits: 0, kind: "mean", about: "", latest: null, mean_30: null, mean_365: null, days: 60 },
        points,
      },
      true,
      english,
      "en",
    );
    expect(found?.now).toBe("55 bpm");
    expect(found?.month).toBe("60 bpm");
    expect(found?.change).toBe("−5 since then");
    expect(found?.best).toBe("55 bpm");
    expect(found?.points).toHaveLength(60);
  });
});
