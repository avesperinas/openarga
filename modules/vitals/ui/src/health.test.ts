import { describe, expect, it } from "vitest";

import type { BodyOverview, CheckupChanges, Figure } from "./api";
import { ageLabel, moving, outChips, weekIndex, weeklyOf, weightMoving } from "./health";
import { english, spanish } from "./i18n/testing";

const figure = (id: string, weeks: (number | null)[]): Figure => ({
  id,
  group: "heart",
  name: id,
  unit: "bpm",
  digits: 0,
  kind: "mean",
  about: "",
  latest: { day: "2026-11-05", value: weeks.at(-1) ?? 0 },
  mean_30: null,
  mean_365: null,
  days: 100,
  weeks,
});

describe("what is changing", () => {
  const steady = Array.from({ length: 22 }, (_, i) => 60 + (i % 2));
  it("shows what departs from its 22 weeks before, most first", () => {
    const overview: BodyOverview = {
      profile: null,
      sections: [
        {
          id: "heart",
          name: "Heart",
          figures: [figure("down", [...steady, 56, 56, 55, 56]), figure("still", [...steady, 60, 61, 60, 61]), figure("short", [56, 56, 55])],
        },
      ],
    };
    const found = moving(overview);
    expect(found.map((one) => one.figure.id)).toEqual(["down"]);
    expect(found[0]?.direction).toBe("down");
  });

  it("the weight, only if it moved half a kilo in 90 days", () => {
    const kpis = (change: number | null) => ({
      steps: { today: null, mean_7: null, mean_7_past: null, mean_30: null, goal: null },
      weight: { average_7: 75, change_30: null, change_90: change, goal: { steps_per_day: null, weight_min_kg: null, weight_max_kg: null, weight_direction: null }, against_goal: null },
      ldl: null,
    });
    expect(weightMoving(kpis(-1.2), english, "en")?.line).toBe("Weight: −1.2 kg in 90 days.");
    expect(weightMoving(kpis(-1.2), spanish, "es")?.line).toContain("1,2 kg");
    expect(weightMoving(kpis(0.3), english, "en")).toBeNull();
  });
});

describe("lab results, with their age", () => {
  const now = new Date("2026-11-05T12:00:00");
  const changes = (day: string): CheckupChanges => ({
    checkup: { id: "c", day, center: null, notes: null, values: 40, out: 1, document: null },
    previous: null,
    changes: [
      { analyte: { id: "glucose", name: "Glucose", panel: "biochemistry", unit: "mg/dL", about: "" }, value: 110, previous: 90, unit: "mg/dL", change: 20, out: true, was_out: false },
    ],
  });

  it("the chips of what is out, only if the check-up is less than a year old", () => {
    expect(outChips(changes("2026-09-02"), english, now)).toEqual([{ id: "glucose", name: "Glucose" }]);
    expect(outChips(changes("2026-09-02"), spanish, now)).toEqual([{ id: "glucose", name: spanish("analyte.glucose.name") }]);
    expect(outChips(changes("2025-09-02"), english, now)).toEqual([]);
  });

  it("how long ago, in words", () => {
    expect(ageLabel("2026-09-02", english, now)).toBe("2 months ago");
    expect(ageLabel("2026-11-04", english, now)).toBe("Yesterday");
    expect(ageLabel("2026-10-29", english, now)).toBe("7 days ago");
  });
});

describe("the weeks of a series", () => {
  it("the last one is this one, from Monday, and a gap is null", () => {
    const now = new Date("2026-11-05T12:00:00");
    expect(weekIndex("2026-11-02", 4, now)).toBe(3);
    expect(weekIndex("2026-10-01", 4, now)).toBeUndefined();
    expect(weeklyOf([{ day: "2026-11-03", value: 10 }, { day: "2026-11-04", value: 20 }], 2, now)).toEqual([null, 15]);
  });
});
