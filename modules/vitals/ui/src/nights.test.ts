import { describe, expect, it } from "vitest";

import type { Night } from "./api";
import { english } from "./i18n/testing";
import { againstUsual, monthsOf, scoreDays, scoreParts, scoreTrend, stageShareList, yearAgo } from "./nights";

const night = (day: string, value: number | null): Night => ({
  day,
  start: `${day}T00:00:00+02:00`,
  end: `${day}T07:00:00+02:00`,
  minutes_asleep: 420,
  minutes_awake: null,
  minutes_in_bed: null,
  minutes_to_fall_asleep: null,
  stages: null,
  nap_minutes: 0,
  score: value === null ? null : { value, quality: value >= 80 ? "good" : "fair", duration: 46, depth: null, calm: null },
});

describe("the nights to draw", () => {
  it("asks for a bit more than a year back", () => {
    expect(yearAgo(new Date(2026, 9, 14))).toBe("2025-10-09");
  });

  it("walks only the months with nights", () => {
    expect(monthsOf([night("2026-10-01", 80), night("2026-08-31", 70), night("2026-10-02", 90)])).toEqual(["2026-08", "2026-10"]);
  });

  it("leaves out the nights without a score", () => {
    expect(scoreDays([night("2026-10-01", 84), night("2026-10-02", null)])).toEqual([{ day: "2026-10-01", value: 84, quality: "good" }]);
  });

  it("the seven-night average starts with three nights", () => {
    const trend = scoreTrend([night("2026-10-01", 60), night("2026-10-02", 90), night("2026-10-03", 90)]);
    expect(trend.map((one) => one.average)).toEqual([null, null, 80]);
  });

  it("puts the stages from awake to deep with their normal", () => {
    const list = stageShareList(
      { stages: { deep: 60, rem: 90, light: 240, awake: 20 } },
      { nights: 3, asleep: 400, stages: { deep: 50 }, fell_asleep_at: null, woke_at: null },
    );
    expect(list.map((one) => [one.stage, one.minutes, one.usual])).toEqual([
      ["awake", 20, null],
      ["rem", 90, null],
      ["light", 240, null],
      ["deep", 60, 50],
    ]);
  });

  it("shows only the parts of the score that could be measured", () => {
    expect(scoreParts({ value: 92, quality: "excellent", duration: 46, depth: null, calm: null }, english)).toEqual([
      { label: "Duration", value: "46 of 50", share: 0.92 },
    ]);
  });

  it("says how much more or less than the normal", () => {
    expect(againstUsual(430, 400, english)).toBe("30 min more than your normal");
    expect(againstUsual(402, 400, english)).toBe("like your normal");
    expect(againstUsual(400, null, english)).toBeUndefined();
  });
});
