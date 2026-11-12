import { describe, expect, it } from "vitest";

import type { BodyOverview, CheckupChanges, Figure } from "./api";
import { ageLabel, moving, outChips, weekIndex, weeklyOf, weightMoving } from "./health";

const figure = (id: string, weeks: (number | null)[]): Figure => ({
  id,
  group: "heart",
  name: id,
  unit: "lpm",
  digits: 0,
  kind: "mean",
  about: "",
  latest: { day: "2026-11-05", value: weeks.at(-1) ?? 0 },
  mean_30: null,
  mean_365: null,
  days: 100,
  weeks,
});

describe("lo que está cambiando", () => {
  const steady = Array.from({ length: 22 }, (_, i) => 60 + (i % 2));
  it("sale lo que se aparta de sus 22 semanas de antes, de más a menos", () => {
    const overview: BodyOverview = {
      profile: null,
      sections: [
        {
          id: "heart",
          name: "Corazón",
          figures: [figure("down", [...steady, 56, 56, 55, 56]), figure("still", [...steady, 60, 61, 60, 61]), figure("short", [56, 56, 55])],
        },
      ],
    };
    const found = moving(overview);
    expect(found.map((one) => one.figure.id)).toEqual(["down"]);
    expect(found[0]?.direction).toBe("down");
  });

  it("el peso, solo si se ha movido medio kilo en 90 días", () => {
    const kpis = (change: number | null) => ({
      steps: { today: null, mean_7: null, mean_7_past: null, mean_30: null, goal: null },
      weight: { average_7: 75, change_30: null, change_90: change, goal: { steps_per_day: null, weight_min_kg: null, weight_max_kg: null, weight_direction: null }, against_goal: null },
      ldl: null,
    });
    expect(weightMoving(kpis(-1.2))?.line).toBe("Peso: −1,2 kg en 90 días.");
    expect(weightMoving(kpis(0.3))).toBeNull();
  });
});

describe("las analíticas, con su antigüedad", () => {
  const now = new Date("2026-11-05T12:00:00");
  const changes = (day: string): CheckupChanges => ({
    checkup: { id: "c", day, center: null, notes: null, values: 40, out: 1, document: null },
    previous: null,
    changes: [
      { analyte: { id: "glucose", name: "Glucosa", panel: "bioquimica", unit: "mg/dL", about: "" }, value: 110, previous: 90, unit: "mg/dL", change: 20, out: true, was_out: false },
    ],
  });

  it("los chips de lo de fuera, solo si la revisión tiene menos de un año", () => {
    expect(outChips(changes("2026-09-02"), now)).toEqual([{ id: "glucose", name: "Glucosa" }]);
    expect(outChips(changes("2025-09-02"), now)).toEqual([]);
  });

  it("cuánto hace, en palabras", () => {
    expect(ageLabel("2026-09-02", now)).toBe("Hace 2 meses");
    expect(ageLabel("2026-11-04", now)).toBe("Ayer");
    expect(ageLabel("2026-10-29", now)).toBe("Hace 7 días");
  });
});

describe("las semanas de una serie", () => {
  it("la última es esta, de lunes, y un hueco es null", () => {
    const now = new Date("2026-11-05T12:00:00");
    expect(weekIndex("2026-11-02", 4, now)).toBe(3);
    expect(weekIndex("2026-10-01", 4, now)).toBeUndefined();
    expect(weeklyOf([{ day: "2026-11-03", value: 10 }, { day: "2026-11-04", value: 20 }], 2, now)).toEqual([null, 15]);
  });
});
