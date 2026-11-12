import { describe, expect, it } from "vitest";

import type { Goal } from "./api";
import { against, byCategory, byDate, condition, figure, standing, subtitle, weekLabel } from "./goalWords";

const TODAY = "2026-10-15";

function goal(fields: Partial<Goal>): Goal {
  return {
    id: "g",
    title: "Meta",
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

const STEPS = { key: "vitals.steps", label: "Pasos", unit: "steps", kind: "amount" as const };
const WEIGHT = { key: "vitals.weight", label: "Peso", unit: "kg", kind: "level" as const };

describe("las cifras, dichas", () => {
  it.each([
    [8000, "steps", "8.000 pasos"],
    [82, "kg", "82,0 kg"],
    [54300, "EUR", "54.300 €"],
    [12.5, "EUR", "12,5 €"],
    [3, "count", "3"],
    [null, "kg", "—"],
  ])("%s %s", (value, unit, expected) => {
    expect(figure(value, unit)).toBe(expected);
  });
});

describe("lo que pide y cómo va", () => {
  it("una periódica atada a los pasos", () => {
    const steps = goal({ metric: STEPS, target: 8000, category: "Salud" });
    expect(condition(steps)).toBe("al menos 8.000 pasos");
    expect(subtitle(steps, TODAY)).toBe("Salud · al menos 8.000 pasos cada día · pasos");
  });

  it("una de cinco días a la semana, a mano, cuenta su racha en semanas", () => {
    const reading = goal({ days_per_week: 5, streak: 3, streak_unit: "weeks" });
    expect(subtitle(reading, TODAY)).toBe("5 días por semana");
    expect(standing(reading)).toEqual({ tone: "neutral", text: "Racha de 3 semanas" });
    expect(weekLabel(reading)).toBe("2 de 5 esta semana");
  });

  it("una con fecha por detrás, con su proyección", () => {
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
    expect(standing(weight)).toEqual({ tone: "negative", text: "Por detrás" });
    expect(against(weight, TODAY)).toBe("de 85 a 80,0 kg · llegas a 83,5 kg");
    expect(subtitle(weight, TODAY)).toBe("peso · 31 dic");
  });

  it("cerradas, dicen cómo acabaron", () => {
    expect(standing(goal({ status: "missed" })).text).toBe("No cumplida");
    expect(standing(goal({ status: "achieved" })).tone).toBe("positive");
  });
});

describe("la portada", () => {
  const goals = [
    goal({ id: "a", kind: "dated", due_on: "2027-06-01", category_id: "c1" }),
    goal({ id: "b", kind: "dated", due_on: "2026-12-31" }),
    goal({ id: "c", category_id: "c1" }),
  ];

  it("por fecha: lo de cada día primero y después lo que antes vence", () => {
    expect(byDate(goals).map((group) => [group.id, group.goals.map((one) => one.id)])).toEqual([
      ["periodic", ["c"]],
      ["dated", ["b", "a"]],
    ]);
  });

  it("por categoría: en su orden, y las que no tienen al final", () => {
    const groups = byCategory(goals, [{ id: "c1", name: "Salud", hue: 6 }]);
    expect(groups.map((group) => [group.label, group.goals.map((one) => one.id)])).toEqual([
      ["Salud", ["c", "a"]],
      ["Sin categoría", ["b"]],
    ]);
  });
});

describe("cómo vas, arriba de las metas (T-B22)", () => {
  it("lo de cada día hecho hoy, lo que va por detrás y la racha más larga", async () => {
    const { goalFigures } = await import("./Goals");
    const figures = goalFigures([
      goal({ id: "a", today_met: true, streak: 4, streak_unit: "days" }),
      goal({ id: "b", today_met: false, streak: 9, streak_unit: "weeks", period: "week" }),
      goal({ id: "c", kind: "dated", period: null, pace: "behind" }),
    ]);
    expect(figures.map((one) => [one.label, one.value])).toEqual([
      ["hechas hoy", "1/1"],
      ["por detrás", 1],
      ["racha (semanas)", 9],
    ]);
    expect(figures[0]!.lit).toBe(true);
  });
});
