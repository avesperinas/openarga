import { describe, expect, it } from "vitest";

import type { Baseline, Load } from "./api";
import { english, spanish } from "./i18n/testing";
import { baselineTile, byName, byWeek, elapsed, fromFirstLoad, groupLine, minutesLabel, rollingMean, zoneShares } from "./workouts";

const base: Baseline = {
  id: "resting_heart_rate",
  name: "Resting HR",
  unit: "bpm",
  digits: 0,
  day: "2026-10-13",
  value: 64,
  mean: 56,
  low: 54,
  high: 58,
  status: "above",
  days: 30,
};

describe("your normal", () => {
  it("outside the band it is said in amber, without judging", () => {
    expect(baselineTile(base, english, "en")).toEqual({
      value: "64 bpm",
      foot: "above your normal · 54 bpm – 58 bpm",
      tone: "warning",
    });
  });

  it("inside, no colour; without 14 days, no comparison; without data, it says so", () => {
    expect(baselineTile({ ...base, value: 56, status: "inside" }, english, "en").tone).toBe("neutral");
    expect(baselineTile({ ...base, status: null, low: null, high: null, days: 9 }, english, "en").foot).toBe(
      "no normal yet (9 of 14 days)",
    );
    expect(baselineTile({ ...base, value: null }, english, "en").foot).toBe("no data from today or yesterday");
  });

  it("sleep goes in hours and temperature with its sign", () => {
    expect(baselineTile({ ...base, unit: "min", value: 425, low: 400, high: 460, status: "inside" }, english, "en").value).toBe(
      "7 h 05",
    );
    expect(baselineTile({ ...base, unit: "°C", digits: 1, value: 0.4, status: "inside" }, english, "en").value).toBe("+0.4 °C");
    expect(baselineTile({ ...base, unit: "°C", digits: 1, value: 0.4, status: "inside" }, spanish, "es").value).toBe("+0,4 °C");
  });
});

describe("the sums of a workout", () => {
  it("minutes and seconds as they read", () => {
    expect(minutesLabel(45)).toBe("45 min");
    expect(minutesLabel(87)).toBe("1 h 27");
    expect(elapsed(725)).toBe("12:05");
  });

  it("the average night of a group in one line", () => {
    expect(groupLine({ nights: 4, asleep: 425, deep: 62, hrv: 38 }, english, "en")).toBe("7 h 05 · deep 1 h 02 · HRV 38 ms · 4 nights");
    expect(groupLine({ nights: 0, asleep: null, deep: null, hrv: null }, english, "en")).toBe("no nights");
  });

});

const week = (start: string, load: number, workouts = 1, zones?: number[]) => ({ start, workouts, minutes: workouts * 60, load, zones });

describe("load per week", () => {
  const load: Load = {
    this_week: 240,
    mean_4: 520,
    weeks: [week("2026-09-28", 0, 0), week("2026-10-05", 0, 2), week("2026-10-12", 800), week("2026-10-19", 550), week("2026-10-26", 760), week("2026-11-02", 240)],
  };

  it("starts at the first week with load", () => {
    expect(fromFirstLoad(load).weeks.map((one) => one.start)).toEqual(["2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02"]);
  });

  it("the average is of the four before, and without four there is none", () => {
    const means = rollingMean(load);
    expect(means.slice(0, 4)).toEqual([null, null, null, null]);
    expect(means[4]).toBe(Math.round((0 + 0 + 800 + 550) / 4));
  });

  it("the zones of the last four, in minutes and as a share of the total", () => {
    const zoned: Load = { ...load, weeks: [week("2026-10-26", 1, 1, [30, 10, 0, 0, 0]), week("2026-11-02", 1, 1, [10, 30, 20, 0, 0])] };
    const { minutes, shares } = zoneShares(zoned);
    expect(minutes).toEqual([40, 40, 20, 0, 0]);
    expect(shares[0]).toBeCloseTo(0.4);
  });
});

describe("what you do and the workouts per week", () => {
  const workout = (name: string, start: string, minutes: number) => ({
    id: `${name}-${start}`,
    kind: "activity" as const,
    name,
    start,
    end: start,
    minutes,
    href: null,
    from_band: true,
    kcal: null,
    heart: { avg: null, max: null, zones: [], load: 0, recovery_2min: null, source: null },
  });
  const now = new Date("2026-11-05T12:00:00");
  const list = [
    workout("Tennis", "2026-11-04T18:00:00", 90),
    workout("Strength", "2026-11-03T19:00:00", 60),
    workout("Tennis", "2026-10-28T18:00:00", 80),
    workout("Cycling", "2026-09-01T10:00:00", 120),
  ];

  it("by name, of the last 30 days and from most minutes to least", () => {
    expect(byName(list, now, english)).toEqual([
      { name: "Tennis", count: 2, minutes: 170 },
      { name: "Strength", count: 1, minutes: 60 },
    ]);
  });

  it("by Monday week, this one first and with its count", () => {
    const weeks = byWeek(list, now, english, "en");
    expect(weeks[0]?.label).toBe("This week · 2");
    expect(weeks[1]?.items.map((one) => one.name)).toEqual(["Tennis"]);
  });
});
