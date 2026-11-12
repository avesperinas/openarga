import { describe, expect, it } from "vitest";

import { pathOf, route } from "./App";
import { byUse, foodChoice, outsideChoice, picked, recipeChoice, usualChoice } from "./AddSheet";
import { coverageNote, figure, goalDetail, kcalLine, macroParts } from "./DayDetail";
import { goalsLine, isMonday, worthProposing } from "./Today";
import { changeLabel, proposalLabel, proposalRange } from "./Expenditure";
import { dayKindLabel, goalLabel, proteinPerKilo } from "./Goals";
import { dailyLabel, menuLine, outdatedLabel } from "./Planning";
import type { Micro } from "./api";
import { dayTitle, doubtLine, drinksLine, quantityLabel, rows, shiftDay } from "./words";
import { coverageGroups, daysNear, kcalTrend, microShare, microValue, windowLine } from "./eating";
import { mealParts } from "./DayDetail";
import { plannedLabel, tookLabel } from "./Today";
import type { Week } from "./api";

describe("las direcciones de Macros", () => {
  it("cada pantalla tiene la suya, y un día pasado también", () => {
    expect(route("/macros/")).toEqual({ tab: "today" });
    expect(route("/macros/dia/2026-09-28")).toEqual({ tab: "today", day: "2026-09-28" });
    expect(route("/macros/semana")).toEqual({ tab: "week" });
    expect(route("/macros/apuntar")).toEqual({ tab: "today", add: true });
    expect(pathOf({ tab: "goals" })).toBe("/macros/objetivo");
    expect(pathOf({ tab: "today", day: "2026-09-28" })).toBe("/macros/dia/2026-09-28");
  });
});

describe("lo que se apunta", () => {
  it("nunca lleva un nutriente: solo qué y cuánto", () => {
    const food = { id: "f1", name: "Lentils", label: "lentejas", source: "usda", nutrients: { kcal: 352 }, grams_per_unit: null, density_g_ml: null };
    expect(foodChoice(food).make(80, "g")).toEqual({ kind: "food", food_id: "f1", quantity: 80, unit: "g" });
    expect(
      outsideChoice({ source: "off", source_ref: "8400000000017", name: "Galletas", brand: null, nutrients: { kcal: 480 } }).make(30, "g"),
    ).toEqual({ kind: "food", source: "off", source_ref: "8400000000017", quantity: 30, unit: "g" });
    expect(recipeChoice({ id: "r1", name: "Lentejas", servings: 4 }).make(2, "serving")).toEqual({
      kind: "recipe",
      recipe_id: "r1",
      quantity: 2,
      unit: "serving",
    });
  });
});

describe("cómo se dicen las cifras", () => {
  it("lo estimado lleva ≈ y las raciones se nombran", () => {
    expect(quantityLabel({ quantity: 150, unit: "ml", estimated: true })).toBe("≈ 150 ml");
    expect(quantityLabel({ quantity: 1, unit: "unit", estimated: false, portion: "envase" })).toBe("1 envase");
    expect(quantityLabel({ quantity: 2, unit: "unit", estimated: true, portion: "loncha" })).toBe("≈ 2 lonchas");
    expect(quantityLabel({ quantity: 2, unit: "serving", estimated: false })).toBe("2 raciones");
    expect(quantityLabel({ quantity: 1, unit: "serving", estimated: false })).toBe("1 ración");
  });

  it("los días cercanos por su nombre", () => {
    expect(dayTitle("2026-09-29", "2026-09-29")).toBe("Hoy");
    expect(dayTitle("2026-09-28", "2026-09-29")).toBe("Ayer");
    expect(shiftDay("2026-09-30", 1)).toBe("2026-10-01");
  });

  it("las bebidas en su cifra, y el agua siempre", () => {
    expect(drinksLine({ caffeine_mg: 60, alcohol_g: 9.8, alcohol_units: 1, water_l: 0.5 })).toBe(
      "60 mg de cafeína · 1 ud de alcohol (9,8 g) · 0,5 l de agua",
    );
    expect(drinksLine({ caffeine_mg: null, alcohol_g: null, alcohol_units: null, water_l: 0 })).toBe("0 l de agua");
  });
});

describe("un micro frente a su referencia", () => {
  const base: Micro = {
    key: "vitamin_d",
    name: "Vitamina D",
    unit: "µg",
    value: 7.5,
    coverage: 1,
    reference: { nutrient: "vitamin_d", kind: "min", value: 15, own: false },
    status: "low",
    partial: false,
    missing: [],
  };

  it("en % de lo recomendado, con la cifra contra la referencia", () => {
    expect(microShare(base, 2000)).toBe(0.5);
    expect(microValue(base, 2000)).toBe("7,5 de 15 µg");
  });

  it("lo de parte de las kcal, contra esa parte", () => {
    const saturated: Micro = { ...base, key: "saturated_fat", name: "Grasa saturada", unit: "g", value: 20, reference: { nutrient: "saturated_fat", kind: "energy_share", value: 0.1, own: false } };
    expect(microShare(saturated, 2000)).toBeCloseTo(0.9);
    expect(microValue(saturated, 2000)).toBe("9 % de las kcal (máx. 10 %)");
  });

  const week = (micros: Micro[]): Week =>
    ({ first: "2026-10-29", last: "2026-11-04", days_logged: 7, averages: { kcal: 2000 }, days: [], micros, profile: { sex: null, age: null, from_health: false }, drinks: { caffeine_mg: null, alcohol_g: null, alcohol_units: null, water_l: 0 }, counted: { days: 7, complete: true } }) as unknown as Week;

  it("en cuatro grupos, y lo de dato incompleto no entra en «Te falta»", () => {
    const sodium: Micro = { ...base, key: "sodium", name: "Sodio", unit: "mg", value: 1900, reference: { nutrient: "sodium", kind: "max", value: 2000, own: false } };
    const folate: Micro = { ...base, key: "folate", name: "Folato", unit: "µg", value: 300, reference: { nutrient: "folate", kind: "min", value: 330, own: false } };
    const partial: Micro = { ...base, key: "zinc", name: "Zinc", partial: true };
    const groups = coverageGroups(week([base, sodium, folate, partial]), null);
    expect(groups.map((one) => [one.key, one.items.map((item) => item.key)])).toEqual([
      ["low", ["vitamin_d"]],
      ["near", ["folate", "zinc"]],
      ["caution", ["sodium"]],
    ]);
  });

  it("las fechas y qué días cuentan", () => {
    expect(windowLine(week([]))).toBe("29 oct – 4 nov · 7 días completos");
  });
});

describe("la tendencia de las kcal", () => {
  it("solo días completos, con la media de los siete de antes", () => {
    const days = Array.from({ length: 14 }, (_, i) => ({ day: `2026-10-${String(i + 10).padStart(2, "0")}`, kcal: 2000 + i * 10, complete: i !== 5 }));
    const points = kcalTrend({ days, weeks: [], nutrients: {} }, 2);
    expect(points).toHaveLength(13);
    expect(points[0]?.average).toBeNull();
    expect(points[6]?.average).toBe(Math.round((2000 + 2010 + 2020 + 2030 + 2040 + 2060 + 2070) / 7));
  });

  it("los días cerca del objetivo", () => {
    const days = [2000, 1700, 2300, null].map((kcal, i) => ({ day: `2026-11-0${i + 1}`, kcal, against_target: "none" as const }));
    expect(daysNear({ days } as unknown as Week, 2000)).toEqual({ near: 1, of: 3 });
  });
});

describe("el peso en Macros", () => {
  it("lee el objetivo de proteína en gramos por kilo, si hay las dos cosas", () => {
    expect(proteinPerKilo(144, 80)).toBe("Tu objetivo de proteína son 1,8 g por kilo. El mismo peso en Salud y en Training.");
    expect(proteinPerKilo(null, 80)).toBeNull();
    expect(proteinPerKilo(144, null)).toBeNull();
  });
});

describe("un suplemento", () => {
  it("se apunta solo en sus unidades, con su nombre", () => {
    const capsule = {
      id: "s1",
      name: "Omega 3",
      label: "omega 3",
      source: "manual",
      nutrients: { kcal: 9 },
      grams_per_unit: null,
      density_g_ml: null,
      nutrients_per: "unit" as const,
      unit_name: "cápsula",
    };
    expect(foodChoice(capsule).units.map((one) => one.label)).toEqual(["cápsula"]);
    expect(foodChoice(capsule).make(2, "unit")).toEqual({ kind: "food", food_id: "s1", quantity: 2, unit: "unit" });
  });
});

describe("la hoja de apuntar", () => {
  const yogurt = {
    id: "y1",
    name: "Yogurt",
    label: "Yogur natural",
    source: "usda",
    nutrients: { kcal: 60, protein: 4 },
    grams_per_unit: null,
    density_g_ml: null,
    portions: { envase: 125, cucharada: 15 },
  };

  it("una medida de casa se apunta como tal y suma sus gramos", () => {
    const choice = foodChoice(yogurt);
    expect(choice.measures.map((one) => one.name)).toEqual(["cucharada", "envase"]);
    const one = picked(choice, 1, "unit", "envase");
    expect(one.item).toEqual({ kind: "food", food_id: "y1", quantity: 1, unit: "unit", portion: "envase" });
    expect(one.label).toBe("1 envase");
    expect(one.kcal).toBe(75);
    expect(one.protein).toBe(5);
  });

  it("lo de la última vez se repite en su medida y suma en proporción", () => {
    const last = {
      name: "Nueces", kind: "food" as const, food_id: "n1", recipe_id: null, quantity: 20, unit: "g" as const,
      grams: 20, kcal: 130, times: 3, item_id: "i1", last_day: "2026-10-28",
    };
    const one = picked(usualChoice(last), 30, "g");
    expect(one.item).toEqual({ kind: "food", food_id: "n1", quantity: 30, unit: "g" });
    expect(one.kcal).toBe(195);
  });

  it("la despensa sale por uso", () => {
    const other = { ...yogurt, id: "y2", label: "Yogur griego" };
    expect(byUse([yogurt, other], new Map([["y2", 5]])).map((one) => one.id)).toEqual(["y2", "y1"]);
  });
});

describe("los objetivos", () => {
  it("se leen como rango, mínimo, tope o % de las kcal", () => {
    const base = { nutrient_unit: "kcal", unit: "amount" as const };
    expect(goalLabel({ ...base, min: 1900, max: 2100 })).toBe("1.900 – 2.100 kcal");
    expect(goalLabel({ unit: "amount", nutrient_unit: "g", min: 25, max: null })).toBe("≥ 25 g");
    expect(goalLabel({ unit: "kcal_pct", nutrient_unit: "g", min: null, max: 7 })).toBe("≤ 7 % de las kcal");
    expect(goalLabel({ unit: "kcal_pct", nutrient_unit: "g", min: 20, max: 35 })).toBe("20 – 35 % de las kcal");
  });

  it("el tipo de día dice por qué", () => {
    expect(dayKindLabel({ day: "2026-10-16", kind: "training", source: "workout", workouts: ["Pull"] })).toBe(
      "Hoy es de entreno: Pull.",
    );
    expect(dayKindLabel({ day: "2026-10-16", kind: "rest", source: "manual", workouts: [] })).toBe(
      "Hoy es de descanso, a mano.",
    );
  });
});

describe("el día por dentro", () => {
  it("dice el objetivo, lo que falta de datos y las kcal por hora", () => {
    expect(goalDetail({ basis: "kcal_pct", min: null, max: 7, unit: "g", share: 9.1 })).toBe(
      "≤ 7 % de las kcal · vas en 9,1 %",
    );
    expect(goalDetail({ basis: "amount", min: 1900, max: 2100, unit: "kcal", share: null })).toBe("1.900 – 2.100 kcal");
    expect(coverageNote(0.55)).toBe("Faltan datos del 45 % de las kcal");
    expect(coverageNote(0.9)).toBeUndefined();
    expect(figure(null, "µg")).toBe("—");
  });

  it("lo planificado y las plantillas se dicen como se leen", () => {
    expect(dailyLabel({ daily_at: "08:00:00" })).toBe("cada día a las 08:00");
    expect(dailyLabel({ daily_at: null })).toBeUndefined();
    expect(outdatedLabel({ recipe_id: "r", name: "Lentejas", items: 3, days: [] })).toBe(
      "Lentejas: 3 registros con la versión anterior",
    );
  });
});

describe("el día de un vistazo", () => {
  it("dice lo que queda o lo que te pasas, y sin objetivo no se inventa", () => {
    expect(kcalLine(1170, 2050)).toBe("quedan 880 de 2.050");
    expect(kcalLine(2170, 2050)).toBe("te pasas 120 de 2.050");
    expect(kcalLine(800, null)).toBe("sin objetivo de kcal");
  });

  it("las macros contra su objetivo, y sin él solo lo comido", () => {
    const target = { valid_from: "2026-11-02", kcal: 2050, protein: 140, carbs: null, fat: 65 };
    const parts = macroParts({ nutrients: { kcal: 1100, protein: 70, carbs: 121, fat: 65 }, target });
    expect(parts.map((part) => [part.label, part.value, part.share])).toEqual([
      ["Proteína", "70 / 140 g", 0.5],
      ["Hidratos", "121 g · 44 % de las kcal", 0.44],
      ["Grasa", "65 / 65 g", 1],
    ]);
  });

  it("con lo planificado, el anillo lo dice", () => {
    expect(kcalLine(320, 2200, 350)).toBe("con lo planificado, 670 de 2.200");
  });

  it("la barra del día por comidas, con lo planificado y lo que queda", () => {
    const meals = [
      { meal: "breakfast", label: "Desayuno", kcal: 400 },
      { meal: "lunch", label: "Comida", kcal: 0 },
    ] as never;
    const planned = [{ nutrients: { kcal: 100 } }] as never;
    const found = mealParts({ meals, target: { valid_from: "x", kcal: 2000, protein: null, carbs: null, fat: null }, planned });
    expect(found.parts.map((one) => one.label)).toEqual(["Desayuno", "Planificado"]);
    expect(found.rest).toEqual({ label: "Queda", value: "1.500", share: 1500 });
  });

  it("confirmar lo planificado dice lo que es", () => {
    expect(tookLabel({ items: [{ unit: "unit", kind: "food" }] } as never)).toBe("Me lo he tomado");
    expect(tookLabel({ items: [{ unit: "g", kind: "food" }] } as never)).toBe("Me lo he comido");
    expect(plannedLabel({ eaten_at: "2026-11-05T22:00:00+01:00", said: "suplementos" })).toBe("Planificado · 22:00 · suplementos");
  });

  it("cuántos objetivos van en zona", () => {
    expect(goalsLine([{ status: "ok" }, { status: "low" }, { status: "none" }])).toBe("1 de 2 en zona");
    expect(goalsLine([])).toBe("Sin objetivos con dato todavía");
  });
});

describe("los menús", () => {
  it("dicen lo que llevan y si se planifican solos", () => {
    expect(menuLine({ items: [{ kind: "water", quantity: 250, unit: "ml" }], daily_at: null })).toBe("1 cosa");
    expect(
      menuLine({
        items: [
          { kind: "water", quantity: 250, unit: "ml" },
          { kind: "water", quantity: 250, unit: "ml" },
        ],
        daily_at: "08:00:00",
      }),
    ).toBe("2 cosas · cada día a las 08:00");
  });
});

describe("las dudas de Claude", () => {
  it("se dicen en su fila", () => {
    expect(doubtLine("first")).toBe("¿Es este? Primera vez que lo apuntas");
    expect(doubtLine("unsure")).toBe("¿Es este? Claude no lo tenía claro");
    expect(doubtLine(null)).toBeUndefined();
  });
});

describe("los objetivos por kilo", () => {
  it("dicen lo puesto y lo que sale con el peso", () => {
    expect(
      goalLabel({ min: 1.8, max: null, unit: "per_kg", nutrient_unit: "g", kg: 77.9, amount: { min: 140.2, max: null } }),
    ).toBe("≥ 1,8 g/kg · 140,2 g con 77,9 kg");
    expect(goalLabel({ min: 1.8, max: null, unit: "per_kg", nutrient_unit: "g" })).toBe("≥ 1,8 g/kg");
  });
});

describe("el gasto estimado", () => {
  it("dice la propuesta, su rango y el peso", () => {
    expect(proposalLabel({ rate_kg_week: -0.3, kcal: 2150, floored: false })).toBe("Para bajar 0,3 kg por semana, 2.150 kcal");
    expect(proposalLabel({ rate_kg_week: 0, kcal: 2450, floored: false })).toBe("Para mantener el peso, 2.450 kcal");
    expect(proposalRange(2150)).toEqual({ min: 2040, max: 2260 });
    expect(changeLabel(-0.24)).toBe("−0,2 kg por semana");
    expect(changeLabel(0.01)).toBe("el peso, igual");
  });

  it("la del lunes sale el lunes y si cambia algo", () => {
    expect(isMonday("2026-11-02")).toBe(true);
    expect(isMonday("2026-11-03")).toBe(false);
    expect(worthProposing(2150, 2100)).toBe(false);
    expect(worthProposing(2150, 2400)).toBe(true);
    expect(worthProposing(2150, null)).toBe(true);
  });
});

describe("los platos sin receta", () => {
  const item = (id: string, dish?: string) => ({ id, dish, name: id }) as never;
  it("juntan solo las líneas seguidas del mismo plato, y dejan sueltas las demás", () => {
    const found = rows([item("a", "Tortita"), item("b", "Tortita"), item("c"), item("d", "Tortita")]);
    expect(found.map((row) => (row.kind === "dish" ? `${row.name}:${row.items.length}` : "suelta"))).toEqual([
      "Tortita:2",
      "suelta",
      "Tortita:1",
    ]);
  });
});
