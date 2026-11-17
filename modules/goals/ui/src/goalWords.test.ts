import { configureRegional, regional } from "@openarga/ui";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Goal } from "./api";
import {
  against,
  byCategory,
  byDate,
  condition,
  figure,
  goalFigures,
  standing,
  subtitle,
  weekLabel,
} from "./goalWords";
import { english, spanish } from "./i18n/testing";

const TODAY = "2026-10-15";

function goal(fields: Partial<Goal>): Goal {
  return {
    id: "g",
    title: "Goal",
    category_id: null,
    category: null,
    hue: null,
    kind: "periodic",
    metric: null,
    direction: "at_least",
    target: null,
    period: "day",
    days_per_week: 7,
    start_value: null,
    start_on: "2026-01-01",
    due_on: null,
    status: "active",
    closed_on: null,
    closed_value: null,
    note: null,
    featured: false,
    position: 1,
    today_met: false,
    today_value: null,
    today_manual: false,
    week: [],
    week_count: 2,
    week_target: 5,
    week_met: false,
    streak: 0,
    streak_unit: "days",
    constancy: null,
    current: null,
    start: null,
    expected: null,
    pace: null,
    progress: null,
    projection: null,
    projection_reached: null,
    reached: null,
    last_day: null,
    days_left: null,
    ...fields,
  };
}

const STEPS = { key: "vitals.steps", label: "Steps", unit: "steps", kind: "amount" as const };
const WEIGHT = { key: "vitals.weight", label: "Weight", unit: "kg", kind: "level" as const };

describe("in English", () => {
  const saved = regional();
  beforeEach(() => configureRegional({ locale: "en-US" }));
  afterEach(() => configureRegional(saved));

  describe("figures, said", () => {
    it.each([
      [8000, "steps", "8,000 steps"],
      [82, "kg", "82.0 kg"],
      [54300, "EUR", "54,300 €"],
      [12.5, "EUR", "12.5 €"],
      [3, "count", "3"],
      [null, "kg", "—"],
    ])("%s %s", (value, unit, expected) => {
      expect(figure(english, value, unit)).toBe(expected);
    });
  });

  describe("what it asks for and how it goes", () => {
    it("a periodic goal tied to steps", () => {
      const steps = goal({ metric: STEPS, target: 8000, category: "Health" });
      expect(condition(english, steps)).toBe("at least 8,000 steps");
      expect(subtitle(english, steps, TODAY)).toBe("Health · at least 8,000 steps every day · steps");
    });

    it("five days a week, by hand, counts its streak in weeks", () => {
      const reading = goal({ days_per_week: 5, streak: 3, streak_unit: "weeks" });
      expect(subtitle(english, reading, TODAY)).toBe("5 days a week");
      expect(standing(english, reading)).toEqual({ tone: "neutral", text: "3-week streak" });
      expect(weekLabel(english, reading)).toBe("2 of 5 this week");
    });

    it("a dated goal behind, with its projection", () => {
      const weight = goal({
        kind: "dated",
        period: null,
        days_per_week: null,
        metric: WEIGHT,
        direction: "at_most",
        target: 80,
        start: 85,
        current: 84,
        pace: "behind",
        projection: 83.5,
        due_on: "2026-12-31",
      });
      expect(standing(english, weight)).toEqual({ tone: "negative", text: "Behind" });
      expect(against(english, weight, TODAY)).toBe("from 85 to 80.0 kg · you reach 83.5 kg");
      expect(subtitle(english, weight, TODAY)).toBe("weight · Dec 31");
    });

    it("closed ones say how they ended", () => {
      expect(standing(english, goal({ status: "missed" })).text).toBe("Missed");
      expect(standing(english, goal({ status: "achieved" })).tone).toBe("positive");
    });
  });
});

describe("in Spanish", () => {
  const saved = regional();
  beforeEach(() => configureRegional({ locale: "es-ES" }));
  afterEach(() => configureRegional(saved));

  it("numbers and units follow the language", () => {
    expect(figure(spanish, 8000, "steps")).toBe(`8.000 ${spanish("unit.steps")}`);
    expect(figure(spanish, 82, "kg")).toBe("82,0 kg");
    expect(weekLabel(spanish, goal({}))).toBe(spanish("week.of", { count: 2, target: 5 }));
  });
});

describe("the front page", () => {
  const goals = [
    goal({ id: "a", kind: "dated", due_on: "2027-06-01", category_id: "c1" }),
    goal({ id: "b", kind: "dated", due_on: "2026-12-31" }),
    goal({ id: "c", category_id: "c1" }),
  ];

  it("by date: the daily ones first and then what is due sooner", () => {
    expect(byDate(english, goals).map((group) => [group.id, group.goals.map((one) => one.id)])).toEqual([
      ["periodic", ["c"]],
      ["dated", ["b", "a"]],
    ]);
  });

  it("by category: in their order, and the ones without one last", () => {
    const groups = byCategory(english, goals, [{ id: "c1", name: "Health", hue: 6 }]);
    expect(groups.map((group) => [group.label, group.goals.map((one) => one.id)])).toEqual([
      ["Health", ["c", "a"]],
      ["No category", ["b"]],
    ]);
  });
});

describe("how you are doing, above the goals (T-B22)", () => {
  it("the daily ones done today, the ones behind and the longest streak", () => {
    const figures = goalFigures(english, [
      goal({ id: "a", today_met: true, streak: 4, streak_unit: "days" }),
      goal({ id: "b", today_met: false, streak: 9, streak_unit: "weeks", period: "week" }),
      goal({ id: "c", kind: "dated", period: null, pace: "behind" }),
    ]);
    expect(figures.map((one) => [one.label, one.value])).toEqual([
      ["done today", "1/1"],
      ["behind", 1],
      ["streak (weeks)", 9],
    ]);
    expect(figures[0]!.lit).toBe(true);
  });
});
