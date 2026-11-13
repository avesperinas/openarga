import { describe, expect, it } from "vitest";

import type { Day } from "./api";
import { english, spanish } from "./i18n/testing";
import { bandFoot, bandLabel, changeTone, extremes, inPeriod, monthsBefore, parseKg, today } from "./weight";

const day = (date: string, kg: number): Day => ({ day: date, kg, avg7: kg });
const noGoal = { steps_per_day: null, weight_min_kg: null, weight_max_kg: null, weight_direction: null };

describe("the period", () => {
  const days = [day("2025-06-01", 84), day("2026-06-15", 81), day("2026-07-01", 80), day("2026-09-20", 79)];

  it("counts back from the last weigh-in", () => {
    expect(inPeriod(days, "3m").map((one) => one.day)).toEqual(["2026-07-01", "2026-09-20"]);
    expect(inPeriod(days, "1y")).toHaveLength(3);
    expect(inPeriod(days, "all")).toHaveLength(4);
    expect(inPeriod([], "3m")).toEqual([]);
  });

  it("subtracts calendar months", () => {
    expect(monthsBefore("2026-09-20", 3)).toBe("2026-06-20");
    expect(monthsBefore("2026-02-10", 12)).toBe("2025-02-10");
  });

  it("says the lightest and the heaviest day", () => {
    expect(extremes(days)).toEqual({ min: days[3], max: days[0] });
    expect(extremes([])).toBeNull();
  });
});

describe("against the goal", () => {
  it("going down is good above the band and bad below it", () => {
    expect(changeTone(-1.2, "above")).toBe("positive");
    expect(changeTone(0.8, "above")).toBe("negative");
    expect(changeTone(0.8, "below")).toBe("positive");
    expect(changeTone(-1.2, null)).toBe("neutral");
    expect(changeTone(null, "above")).toBe("neutral");
  });

  it("says in kilos how far it is, and the band as it reads", () => {
    const band = { steps_per_day: null, weight_min_kg: 72, weight_max_kg: 76, weight_direction: null };

    expect(bandFoot(78.5, band, "above", english, "en")).toBe("2.5 kg above the goal");
    expect(bandFoot(78.5, band, "above", spanish, "es")).toContain("2,5 kg");
    expect(bandFoot(74, band, "inside", english, "en")).toBe("Within the goal");
    expect(bandFoot(74, noGoal, null, english, "en")).toBe("No goal");
    expect(bandLabel(band, english, "en")).toBe("Between 72.0 kg and 76.0 kg");
    expect(bandLabel({ ...noGoal, weight_max_kg: 76 }, english, "en")).toBe("Up to 76.0 kg");
  });
});

describe("what is typed", () => {
  it("accepts a comma or a dot and rejects what is not a weight", () => {
    expect(parseKg("78,4")).toBe(78.4);
    expect(parseKg(" 78.4 ")).toBe(78.4);
    expect(parseKg("8,1")).toBeNull();
    expect(parseKg("a lot")).toBeNull();
  });

  it("today is today in the time zone of the person", () => {
    expect(today("Europe/Madrid", new Date("2026-09-25T22:30:00Z"))).toBe("2026-09-26");
    expect(today("America/New_York", new Date("2026-09-25T22:30:00Z"))).toBe("2026-09-25");
  });
});
