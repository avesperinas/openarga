import { configureRegional } from "@openarga/ui";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { pathOf, route } from "./App";
import { byUse, foodChoice, outsideChoice, picked, recipeChoice, usualChoice } from "./AddSheet";
import { coverageNote, figure, goalDetail, kcalLine, macroParts, mealParts } from "./DayDetail";
import { changeLabel, proposalLabel, proposalRange } from "./Expenditure";
import { dayKindLabel, goalLabel, proteinPerKilo } from "./Goals";
import { english as t, spanish } from "./i18n/testing";
import { dailyLabel, menuLine, outdatedLabel } from "./Planning";
import { goalsLine, isMonday, plannedLabel, tookLabel, worthProposing } from "./Today";
import type { Micro, Week } from "./api";
import { coverageGroups, daysNear, kcalTrend, microShare, microValue, windowLine } from "./eating";
import { dayTitle, doubtLine, drinksLine, quantityLabel, rows, shiftDay } from "./words";

beforeAll(() => configureRegional({ locale: "en-US", timeZone: "Europe/Madrid", currency: "EUR" }));
afterAll(() => configureRegional({ locale: "es-ES", timeZone: "Europe/Madrid", currency: "EUR" }));

describe("the Macros addresses", () => {
  it("every screen has its own, and so does a past day", () => {
    expect(route("/macros/")).toEqual({ tab: "today" });
    expect(route("/macros/day/2026-09-28")).toEqual({ tab: "today", day: "2026-09-28" });
    expect(route("/macros/week")).toEqual({ tab: "week" });
    expect(route("/macros/log")).toEqual({ tab: "today", add: true });
    expect(pathOf({ tab: "goals" })).toBe("/macros/goals");
    expect(pathOf({ tab: "today", day: "2026-09-28" })).toBe("/macros/day/2026-09-28");
  });
});

describe("what is logged", () => {
  it("never carries a nutrient: only what and how much", () => {
    const food = { id: "f1", name: "Lentils", label: "lentils", source: "usda", nutrients: { kcal: 352 }, grams_per_unit: null, density_g_ml: null };
    expect(foodChoice(food, t).make(80, "g")).toEqual({ kind: "food", food_id: "f1", quantity: 80, unit: "g" });
    expect(
      outsideChoice({ source: "off", source_ref: "8400000000017", name: "Biscuits", brand: null, nutrients: { kcal: 480 } }).make(30, "g"),
    ).toEqual({ kind: "food", source: "off", source_ref: "8400000000017", quantity: 30, unit: "g" });
    expect(recipeChoice({ id: "r1", name: "Lentil stew", servings: 4 }, t).make(2, "serving")).toEqual({
      kind: "recipe",
      recipe_id: "r1",
      quantity: 2,
      unit: "serving",
    });
  });
});

describe("how figures are said", () => {
  it("estimates carry ≈ and servings are named", () => {
    expect(quantityLabel({ quantity: 150, unit: "ml", estimated: true }, t, "en")).toBe("≈ 150 ml");
    expect(quantityLabel({ quantity: 1, unit: "unit", estimated: false, portion: "pot" }, t, "en")).toBe("1 pot");
    expect(quantityLabel({ quantity: 2, unit: "unit", estimated: true, portion: "slice" }, t, "en")).toBe("≈ 2 slices");
    expect(quantityLabel({ quantity: 2, unit: "serving", estimated: false }, t, "en")).toBe("2 servings");
    expect(quantityLabel({ quantity: 1, unit: "serving", estimated: false }, t, "en")).toBe("1 serving");
  });

  it("nearby days by their name", () => {
    expect(dayTitle("2026-09-29", "2026-09-29", t, "en")).toBe("Today");
    expect(dayTitle("2026-09-28", "2026-09-29", t, "en")).toBe("Yesterday");
    expect(shiftDay("2026-09-30", 1)).toBe("2026-10-01");
  });

  it("drinks in their own figure, and water always", () => {
    expect(drinksLine({ caffeine_mg: 60, alcohol_g: 9.8, alcohol_units: 1, water_l: 0.5 }, t)).toBe(
      "60 mg of caffeine · 1 u of alcohol (9.8 g) · 0.5 l of water",
    );
    expect(drinksLine({ caffeine_mg: null, alcohol_g: null, alcohol_units: null, water_l: 0 }, t)).toBe("0 l of water");
  });

  it("in Spanish, with Spanish numbers", () => {
    configureRegional({ locale: "es-ES" });
    try {
      expect(quantityLabel({ quantity: 2, unit: "serving", estimated: false }, spanish, "es")).toBe(
        spanish("unit.serving.other", { amount: "2" }),
      );
      expect(dayTitle("2026-09-29", "2026-09-29", spanish, "es")).toBe(spanish("day.today"));
      expect(drinksLine({ caffeine_mg: null, alcohol_g: null, alcohol_units: null, water_l: 0.5 }, spanish)).toBe(
        spanish("drinks.water", { litres: "0,5" }),
      );
    } finally {
      configureRegional({ locale: "en-US" });
    }
  });
});

describe("a micro against its reference", () => {
  const base: Micro = {
    key: "vitamin_d",
    name: "Vitamin D",
    unit: "µg",
    value: 7.5,
    coverage: 1,
    reference: { nutrient: "vitamin_d", kind: "min", value: 15, own: false },
    status: "low",
    partial: false,
    missing: [],
  };

  it("as a share of the recommendation, with the figure against the reference", () => {
    expect(microShare(base, 2000)).toBe(0.5);
    expect(microValue(base, 2000, t)).toBe("7.5 of 15 µg");
  });

  it("a share of kcal, against that share", () => {
    const saturated: Micro = { ...base, key: "saturated_fat", name: "Saturated fat", unit: "g", value: 20, reference: { nutrient: "saturated_fat", kind: "energy_share", value: 0.1, own: false } };
    expect(microShare(saturated, 2000)).toBeCloseTo(0.9);
    expect(microValue(saturated, 2000, t)).toBe("9 % of kcal (max. 10 %)");
  });

  const week = (micros: Micro[]): Week =>
    ({ first: "2026-10-29", last: "2026-11-04", days_logged: 7, averages: { kcal: 2000 }, days: [], micros, profile: { sex: null, age: null, from_health: false }, drinks: { caffeine_mg: null, alcohol_g: null, alcohol_units: null, water_l: 0 }, counted: { days: 7, complete: true } }) as unknown as Week;

  it("in four groups, and partial data does not go into “Short”", () => {
    const sodium: Micro = { ...base, key: "sodium", name: "Sodium", unit: "mg", value: 1900, reference: { nutrient: "sodium", kind: "max", value: 2000, own: false } };
    const folate: Micro = { ...base, key: "folate", name: "Folate", unit: "µg", value: 300, reference: { nutrient: "folate", kind: "min", value: 330, own: false } };
    const partial: Micro = { ...base, key: "zinc", name: "Zinc", partial: true };
    const groups = coverageGroups(week([base, sodium, folate, partial]), null, t);
    expect(groups.map((one) => [one.key, one.items.map((item) => item.key)])).toEqual([
      ["low", ["vitamin_d"]],
      ["near", ["folate", "zinc"]],
      ["caution", ["sodium"]],
    ]);
  });

  it("the dates and which days count", () => {
    expect(windowLine(week([]), t)).toBe("Oct 29 – Nov 4 · 7 complete days");
  });
});

describe("the kcal trend", () => {
  it("only complete days, with the average of the seven before", () => {
    const days = Array.from({ length: 14 }, (_, i) => ({ day: `2026-10-${String(i + 10).padStart(2, "0")}`, kcal: 2000 + i * 10, complete: i !== 5 }));
    const points = kcalTrend({ days, weeks: [], nutrients: {} }, 2);
    expect(points).toHaveLength(13);
    expect(points[0]?.average).toBeNull();
    expect(points[6]?.average).toBe(Math.round((2000 + 2010 + 2020 + 2030 + 2040 + 2060 + 2070) / 7));
  });

  it("the days close to the goal", () => {
    const days = [2000, 1700, 2300, null].map((kcal, i) => ({ day: `2026-11-0${i + 1}`, kcal, against_target: "none" as const }));
    expect(daysNear({ days } as unknown as Week, 2000)).toEqual({ near: 1, of: 3 });
  });
});

describe("weight in Macros", () => {
  it("reads the protein goal in grams per kilo, if both are there", () => {
    expect(proteinPerKilo(144, 80, t)).toBe(t("goal.protein_per_kg", { grams: "1.8" }));
    expect(proteinPerKilo(null, 80, t)).toBeNull();
    expect(proteinPerKilo(144, null, t)).toBeNull();
  });
});

describe("a supplement", () => {
  it("is logged only in its units, with its name", () => {
    const capsule = {
      id: "s1",
      name: "Omega 3",
      label: "omega 3",
      source: "manual",
      nutrients: { kcal: 9 },
      grams_per_unit: null,
      density_g_ml: null,
      nutrients_per: "unit" as const,
      unit_name: "capsule",
    };
    expect(foodChoice(capsule, t).units.map((one) => one.label)).toEqual(["capsule"]);
    expect(foodChoice(capsule, t).make(2, "unit")).toEqual({ kind: "food", food_id: "s1", quantity: 2, unit: "unit" });
  });
});

describe("the log sheet", () => {
  const yogurt = {
    id: "y1",
    name: "Yogurt",
    label: "Plain yoghurt",
    source: "usda",
    nutrients: { kcal: 60, protein: 4 },
    grams_per_unit: null,
    density_g_ml: null,
    portions: { pot: 125, spoon: 15 },
  };

  it("a household measure is logged as such and adds its grams", () => {
    const choice = foodChoice(yogurt, t);
    expect(choice.measures.map((one) => one.name)).toEqual(["spoon", "pot"]);
    const one = picked(choice, 1, "unit", t, "en", "pot");
    expect(one.item).toEqual({ kind: "food", food_id: "y1", quantity: 1, unit: "unit", portion: "pot" });
    expect(one.label).toBe("1 pot");
    expect(one.kcal).toBe(75);
    expect(one.protein).toBe(5);
  });

  it("last time's thing repeats in its measure and adds in proportion", () => {
    const last = {
      name: "Walnuts", kind: "food" as const, food_id: "n1", recipe_id: null, quantity: 20, unit: "g" as const,
      grams: 20, kcal: 130, times: 3, item_id: "i1", last_day: "2026-10-28",
    };
    const one = picked(usualChoice(last, t), 30, "g", t, "en");
    expect(one.item).toEqual({ kind: "food", food_id: "n1", quantity: 30, unit: "g" });
    expect(one.kcal).toBe(195);
  });

  it("the pantry comes out by use", () => {
    const other = { ...yogurt, id: "y2", label: "Greek yoghurt" };
    expect(byUse([yogurt, other], new Map([["y2", 5]])).map((one) => one.id)).toEqual(["y2", "y1"]);
  });
});

describe("the goals", () => {
  it("read as a range, a minimum, a cap or a share of kcal", () => {
    const base = { nutrient_unit: "kcal", unit: "amount" as const };
    expect(goalLabel({ ...base, min: 1900, max: 2100 }, t)).toBe("1,900 – 2,100 kcal");
    expect(goalLabel({ unit: "amount", nutrient_unit: "g", min: 25, max: null }, t)).toBe("≥ 25 g");
    expect(goalLabel({ unit: "kcal_pct", nutrient_unit: "g", min: null, max: 7 }, t)).toBe("≤ 7 % of kcal");
    expect(goalLabel({ unit: "kcal_pct", nutrient_unit: "g", min: 20, max: 35 }, t)).toBe("20 – 35 % of kcal");
  });

  it("the kind of day says why", () => {
    expect(dayKindLabel({ day: "2026-10-16", kind: "training", source: "workout", workouts: ["Pull"] }, t)).toBe(
      "Today is a training day: Pull.",
    );
    expect(dayKindLabel({ day: "2026-10-16", kind: "rest", source: "manual", workouts: [] }, t)).toBe(
      "Today is a rest day, set by hand.",
    );
  });
});

describe("the day inside", () => {
  it("says the goal, the missing data and the kcal by hour", () => {
    expect(goalDetail({ basis: "kcal_pct", min: null, max: 7, unit: "g", share: 9.1 }, t)).toBe(
      "≤ 7 % of kcal · now at 9.1 %",
    );
    expect(goalDetail({ basis: "amount", min: 1900, max: 2100, unit: "kcal", share: null }, t)).toBe("1,900 – 2,100 kcal");
    expect(coverageNote(0.55, t)).toBe("Data missing for 45 % of kcal");
    expect(coverageNote(0.9, t)).toBeUndefined();
    expect(figure(null, "µg")).toBe("—");
  });

  it("planned things and templates are said as they read", () => {
    expect(dailyLabel({ daily_at: "08:00:00" }, t)).toBe("every day at 08:00");
    expect(dailyLabel({ daily_at: null }, t)).toBeUndefined();
    expect(outdatedLabel({ recipe_id: "r", name: "Lentil stew", items: 3, days: [] }, t)).toBe(
      "Lentil stew: 3 records with the previous version",
    );
  });
});

describe("the day at a glance", () => {
  it("says what is left or how much over, and without a goal it invents nothing", () => {
    expect(kcalLine(1170, 2050, t)).toBe("880 of 2,050 left");
    expect(kcalLine(2170, 2050, t)).toBe("120 over 2,050");
    expect(kcalLine(800, null, t)).toBe("no kcal goal");
  });

  it("the macros against their goal, and without one only what was eaten", () => {
    const target = { valid_from: "2026-11-02", kcal: 2050, protein: 140, carbs: null, fat: 65 };
    const parts = macroParts({ nutrients: { kcal: 1100, protein: 70, carbs: 121, fat: 65 }, target }, t);
    expect(parts.map((part) => [part.label, part.value, part.share])).toEqual([
      ["Protein", "70 / 140 g", 0.5],
      ["Carbs", "121 g · 44 % of kcal", 0.44],
      ["Fat", "65 / 65 g", 1],
    ]);
  });

  it("with what is planned, the ring says so", () => {
    expect(kcalLine(320, 2200, t, 350)).toBe("with what is planned, 670 of 2,200");
  });

  it("the day's bar by meal, with what is planned and what is left", () => {
    const meals = [
      { meal: "breakfast", label: "Breakfast", kcal: 400 },
      { meal: "lunch", label: "Lunch", kcal: 0 },
    ] as never;
    const planned = [{ nutrients: { kcal: 100 } }] as never;
    const found = mealParts({ meals, target: { valid_from: "x", kcal: 2000, protein: null, carbs: null, fat: null }, planned }, t);
    expect(found.parts.map((one) => one.label)).toEqual(["Breakfast", "Planned"]);
    expect(found.rest).toEqual({ label: "Left", value: "1,500", share: 1500 });
  });

  it("confirming what is planned says what it is", () => {
    expect(tookLabel({ items: [{ unit: "unit", kind: "food" }] } as never, t)).toBe("I took it");
    expect(tookLabel({ items: [{ unit: "g", kind: "food" }] } as never, t)).toBe("I ate it");
    expect(plannedLabel({ eaten_at: "2026-11-05T22:00:00+01:00", said: "supplements" }, t)).toBe("Planned · 10:00 PM · supplements");
  });

  it("how many goals are in range", () => {
    expect(goalsLine([{ status: "ok" }, { status: "low" }, { status: "none" }], t)).toBe("1 of 2 in range");
    expect(goalsLine([], t)).toBe("No goals with data yet");
  });
});

describe("the menus", () => {
  it("say what they hold and whether they plan themselves", () => {
    expect(menuLine({ items: [{ kind: "water", quantity: 250, unit: "ml" }], daily_at: null }, t)).toBe("1 thing");
    expect(
      menuLine(
        {
          items: [
            { kind: "water", quantity: 250, unit: "ml" },
            { kind: "water", quantity: 250, unit: "ml" },
          ],
          daily_at: "08:00:00",
        },
        t,
      ),
    ).toBe("2 things · every day at 08:00");
  });
});

describe("the assistant's doubts", () => {
  it("are said in their row", () => {
    expect(doubtLine("first", t)).toBe("Is this it? First time you log it");
    expect(doubtLine("unsure", t)).toBe("Is this it? The assistant was not sure");
    expect(doubtLine(null, t)).toBeUndefined();
  });
});

describe("goals per kilo", () => {
  it("say what was set and what comes out with the weight", () => {
    expect(
      goalLabel({ min: 1.8, max: null, unit: "per_kg", nutrient_unit: "g", kg: 77.9, amount: { min: 140.2, max: null } }, t),
    ).toBe("≥ 1.8 g/kg · 140.2 g at 77.9 kg");
    expect(goalLabel({ min: 1.8, max: null, unit: "per_kg", nutrient_unit: "g" }, t)).toBe("≥ 1.8 g/kg");
  });
});

describe("the estimated expenditure", () => {
  it("says the proposal, its range and the weight", () => {
    expect(proposalLabel({ rate_kg_week: -0.3, kcal: 2150, floored: false }, t)).toBe("To lose 0.3 kg a week, 2,150 kcal");
    expect(proposalLabel({ rate_kg_week: 0, kcal: 2450, floored: false }, t)).toBe("To keep your weight, 2,450 kcal");
    expect(proposalRange(2150)).toEqual({ min: 2040, max: 2260 });
    expect(changeLabel(-0.24, t)).toBe("−0.2 kg a week");
    expect(changeLabel(0.01, t)).toBe("weight unchanged");
  });

  it("Monday's comes on Monday and only if something changes", () => {
    expect(isMonday("2026-11-02")).toBe(true);
    expect(isMonday("2026-11-03")).toBe(false);
    expect(worthProposing(2150, 2100)).toBe(false);
    expect(worthProposing(2150, 2400)).toBe(true);
    expect(worthProposing(2150, null)).toBe(true);
  });
});

describe("dishes without a recipe", () => {
  const item = (id: string, dish?: string) => ({ id, dish, name: id }) as never;
  it("group only consecutive lines of the same dish, and leave the rest loose", () => {
    const found = rows([item("a", "Pancake"), item("b", "Pancake"), item("c"), item("d", "Pancake")]);
    expect(found.map((row) => (row.kind === "dish" ? `${row.name}:${row.items.length}` : "loose"))).toEqual([
      "Pancake:2",
      "loose",
      "Pancake:1",
    ]);
  });
});
