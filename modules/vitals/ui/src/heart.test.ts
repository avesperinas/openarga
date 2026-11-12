import { describe, expect, it } from "vitest";

import { heartSeries, minuteLabel, heartSummary } from "./heart";

describe("la curva del vitals", () => {
  it("dice cada tramo por su hora", () => {
    expect(minuteLabel(0)).toBe("00:00");
    expect(minuteLabel(485)).toBe("08:05");
  });

  it("da el máximo, la media y el mínimo de cada tramo", () => {
    const series = heartSeries([
      { minute: 480, min: 55, avg: 58, max: 63 },
      { minute: 485, min: 60, avg: 75, max: 92 },
    ]);
    expect(series.map((one) => [one.key, one.values])).toEqual([
      ["max", [63, 92]],
      ["avg", [58, 75]],
      ["min", [55, 60]],
    ]);
  });
});

describe("el corazón en el tiempo", () => {
  it("compara la media de ahora con la de hace un mes y busca la más baja", () => {
    const points = Array.from({ length: 60 }, (_, index) => {
      const day = new Date(Date.UTC(2026, 7, 16 + index)).toISOString().slice(0, 10);
      return { day, value: index < 30 ? 60 : 55 };
    });
    const found = heartSummary(
      {
        figure: { id: "resting_heart_rate", group: "heart", name: "FC en reposo", unit: "lpm", digits: 0, kind: "mean", about: "", latest: null, mean_30: null, mean_365: null, days: 60 },
        points,
      },
      true,
    );
    expect(found?.now).toBe("55 lpm");
    expect(found?.month).toBe("60 lpm");
    expect(found?.change).toBe("−5 desde entonces");
    expect(found?.best).toBe("55 lpm");
    expect(found?.points).toHaveLength(60);
  });
});
